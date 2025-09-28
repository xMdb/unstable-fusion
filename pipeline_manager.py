# GENERATIVE AI DISCLAIMER
#
# A portion of this code was generated with the assistance of generative AI. Any files that do not contain a disclaimer were either written by a human without AI assistance or generated with developer tooling such as Vite.

import os
import threading
from queue import Queue, Empty
from typing import Dict, Optional, Any
from config import ALLOWED_MODELS, MAX_CONCURRENT

# Lazy imports - only import heavy ML libraries when needed
_torch = None
_StableDiffusionPipeline = None
_ml_imports_initialized = False

def _ensure_ml_imports():
    """Lazy import of heavy ML libraries"""
    global _torch, _StableDiffusionPipeline, _ml_imports_initialized
    
    if _ml_imports_initialized:
        return
    
    print("⏳ Loading ML libraries (this may take a moment)...")
    import time
    start_time = time.time()
    
    import torch
    from diffusers import StableDiffusionPipeline
    
    _torch = torch
    _StableDiffusionPipeline = StableDiffusionPipeline
    _ml_imports_initialized = True
    
    load_time = time.time() - start_time
    print(f"✓ ML libraries loaded ({load_time:.2f}s)")
    
    # Set torch threads after import
    _torch.set_num_threads(_torch.get_num_threads())

# Pipeline pools and threading infrastructure
pipelines_pools: Dict[str, Queue] = {}  # model_name -> Queue[StableDiffusionPipeline]
pipelines_lock = threading.Lock()
pipeline_init_lock = threading.Lock()

# Thread-safe counter for in-use pipelines
in_use_counter = 0
in_use_counter_lock = threading.Lock()

# Concurrency control
from threading import Semaphore
semaphore = Semaphore(MAX_CONCURRENT)

def create_pipeline_instance(model_name: str):
    """
    Create a new StableDiffusionPipeline instance for the given model_name.
    If loading fails, raises Exception to be caught by caller.
    """
    _ensure_ml_imports()
    
    # safety_checker disabled due to too many false positives
    # it probably should be enabled in a production system to prevent "harmful content"
    # this will also show a warning on model load
    pipe = _StableDiffusionPipeline.from_pretrained(
        model_name, 
        torch_dtype=_torch.float32, 
        safety_checker=None
    )
    pipe = pipe.to("cpu")
    pipe.enable_attention_slicing()
    return pipe

def ensure_pool_for_model(model_name: str):
    """
    Ensure there's a Queue pool for model_name with MAX_CONCURRENT pipeline instances.
    This is lazy-loaded; pool init can be heavy (loads model MAX_CONCURRENT times).
    """
    with pipeline_init_lock:
        if model_name in pipelines_pools:
            return pipelines_pools[model_name]
        
        q = Queue(maxsize=MAX_CONCURRENT)
        # Create up to MAX_CONCURRENT instances and push into queue
        # If any instance fails to load then raise exception
        created = []
        try:
            for i in range(MAX_CONCURRENT):
                inst = create_pipeline_instance(model_name)
                created.append(inst)
                q.put(inst)
        except Exception as e:
            # cleanup created pipelines if possible
            raise RuntimeError(f"Failed to load model '{model_name}': {e}")
        
        pipelines_pools[model_name] = q
        return q

def checkout_pipeline(model_name: str, timeout: float = 30.0):
    """
    Acquire a pipeline instance from the model pool (blocking up to timeout).
    Returns pipeline instance; caller MUST return it with return_pipeline().
    """
    q = ensure_pool_for_model(model_name)
    try:
        pipe = q.get(timeout=timeout)
        return pipe
    except Empty:
        raise RuntimeError("No pipeline instance available within timeout")

def return_pipeline(model_name: str, pipe):
    """
    Return a pipeline instance back into its pool.
    """
    q = pipelines_pools.get(model_name)
    if q is None:
        # drop silently
        return
    q.put(pipe)

def generate_with_pipeline(job_prompt: str, width: int, height: int, steps: int, model_name: str, out_path: str):
    """
    Checkout pipeline instance from pool, run generation, save to out_path, and return.
    Errors propagate to caller.
    """
    pipe = None
    try:
        pipe = checkout_pipeline(model_name, timeout=30.0)
        result = pipe(job_prompt, height=height, width=width, num_inference_steps=steps)
        img = result.images[0]
        img.save(out_path)
        return out_path
    finally:
        if pipe is not None:
            # return pipeline to pool even if generation failed
            return_pipeline(model_name, pipe)

def get_pipeline_status():
    """Get current pipeline status for monitoring"""
    with in_use_counter_lock:
        in_use = in_use_counter
    
    return {
        "concurrency_limit": MAX_CONCURRENT,
        "in_use": in_use,
        "models_loaded": list(pipelines_pools.keys())
    }

def acquire_processing_slot():
    """Acquire a processing slot (semaphore)"""
    return semaphore.acquire(timeout=1.0)

def release_processing_slot():
    """Release a processing slot (semaphore)"""
    semaphore.release()

def increment_in_use():
    """Thread-safe increment of in-use counter"""
    global in_use_counter
    with in_use_counter_lock:
        in_use_counter += 1

def decrement_in_use():
    """Thread-safe decrement of in-use counter"""
    global in_use_counter
    with in_use_counter_lock:
        in_use_counter = max(0, in_use_counter - 1)

# Torch setup is now handled in _ensure_ml_imports() when needed