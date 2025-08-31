// GENERATIVE AI DISCLAIMER
//
// A portion of this code was generated with the assistance of generative AI. Any files that do not contain a disclaimer were either written by a human without AI assistance or generated with developer tooling such as Vite.
//
// Models used:
// GPT-5 by OpenAI (August 2025 version)
// Used for the first draft.
// 
// Claude Sonnet 4 by Anthropic (August 2025 version)
// Used in Agent and Ask mode to adapt the first draft into what you see here, including adding features like dark mode, image liking, and pagination.
//
// GPT-4.1 Copilot by OpenAI (August 2025 VS Code version)
// Used in the IDE to suggest code completions.
//

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Heart, Moon, Sun, Download, X, Calendar, Eye } from "lucide-react";

const API_BASE = "/"; // same domain

// Cookie utilities
const getCookie = (name: string): string | null => {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop()?.split(';').shift() || null;
  return null;
};

const setCookie = (name: string, value: string, days: number = 30): void => {
  const expires = new Date(Date.now() + days * 864e5).toUTCString();
  document.cookie = `${name}=${value}; expires=${expires}; path=/`;
};

// Helper to create authenticated image URL
const getAuthenticatedImageUrl = (imageId: string, token: string): string => {
  return `${API_BASE}images/${imageId}/download?token=${encodeURIComponent(token)}`;
};

// Helper to download image with authentication
const downloadImage = async (imageId: string, token: string): Promise<void> => {
  try {
    const url = `${API_BASE}images/${imageId}/download?token=${encodeURIComponent(token)}`;
    const a = document.createElement('a');
    a.href = url;
    a.download = `image-${imageId}.jpg`;
    a.target = '_blank';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  } catch (error) {
    console.error('Failed to download image:', error);
  }
};

interface Job {
  id: string;
  prompt: string;
  status: string;
  output_path?: string;
  created_at: string;
  model_name: string;
}

interface Image {
  id: string;
  path: string;
  prompt: string;
  likes_count: number;
  created_at: string;
  liked_by_user?: boolean;
  model_name: string;
}

interface QueueData {
  concurrency_limit: number;
  in_use: number;
  queued: number;
  processing: number;
  done: number;
  next_jobs: Job[];
}

export default function App() {
  const [token, setToken] = useState<string | null>(null);
  const [username, setUsername] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [prompt, setPrompt] = useState<string>("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [images, setImages] = useState<Image[]>([]);
  const [imagesPage, setImagesPage] = useState<number>(0);
  const [imagesLimit] = useState<number>(12);
  const [hasMoreImages, setHasMoreImages] = useState<boolean>(true);
  const [promptFilter, setPromptFilter] = useState<string>("");
  const [queue, setQueue] = useState<QueueData | null>(null);
  const [model, setModel] = useState<string>("CompVis/stable-diffusion-v1-4");
  const [width, setWidth] = useState<number>(256);
  const [height, setHeight] = useState<number>(256);
  const [steps, setSteps] = useState<number>(20);
  const [isDarkMode, setIsDarkMode] = useState<boolean>(() => {
    const saved = getCookie('darkMode');
    const initial = saved ? saved === 'true' : false;
    // Apply dark mode class immediately
    if (initial) {
      document.documentElement.classList.add('dark');
    }
    return initial;
  });
  const [isSubmittingJob, setIsSubmittingJob] = useState<boolean>(false);
  const [activePolling, setActivePolling] = useState<{jobs: boolean, images: boolean, queue: boolean}>({
    jobs: false,
    images: false,
    queue: false
  });

  // Toggle dark mode
  const toggleDarkMode = () => {
    const newMode = !isDarkMode;
    setIsDarkMode(newMode);
    setCookie('darkMode', newMode.toString());
    document.documentElement.classList.toggle('dark', newMode);
  };

  async function login(): Promise<void> {
    const body = new URLSearchParams({ username, password });
    const res = await fetch(API_BASE + "auth/token", {
      method: "POST",
      body,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    const data = await res.json();
    setToken(data.access_token);
  }

  async function submitJob(): Promise<void> {
    if (!token || !prompt.trim()) return;
    
    setIsSubmittingJob(true);
    try {
      const res = await fetch(API_BASE + "jobs", {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ prompt, width, height, steps, model_name: model })
      });
      const job: Job = await res.json();
      setJobs([job, ...jobs]);
      setPrompt("");
      
      // Start polling jobs after submitting
      setActivePolling(prev => ({ ...prev, jobs: true }));
    } finally {
      setIsSubmittingJob(false);
    }
  }

  async function refreshJobs(): Promise<void> {
    if (!token) return;
    
    const res = await fetch(API_BASE + "jobs", { headers: { Authorization: `Bearer ${token}` } });
    const data: Job[] = await res.json();
    setJobs(data);
    
    // Stop polling if no jobs are processing or queued
    const hasActiveJobs = data.some(job => job.status === 'queued' || job.status === 'processing');
    if (!hasActiveJobs) {
      setActivePolling(prev => ({ ...prev, jobs: false }));
    }
  }

  async function refreshImages(page: number = 0, filter: string = "", append: boolean = false): Promise<void> {
    if (!token) return;
    
    const skip = page * imagesLimit;
    const params = new URLSearchParams({
      skip: skip.toString(),
      limit: imagesLimit.toString(),
    });
    
    if (filter.trim()) {
      params.append('prompt_contains', filter.trim());
    }
    
    const res = await fetch(`${API_BASE}images?${params}`, { 
      headers: { Authorization: `Bearer ${token}` } 
    });
    const data: Image[] = await res.json();
    
    if (append) {
      setImages(prev => [...prev, ...data]);
    } else {
      setImages(data);
    }
    
    // Check if there are more images
    setHasMoreImages(data.length === imagesLimit);
  }

  async function refreshQueue(): Promise<void> {
    if (!token) return;
    
    const res = await fetch(API_BASE + "queue", { headers: { Authorization: `Bearer ${token}` } });
    const data: QueueData = await res.json();
    setQueue(data);
  }

  async function cancelJob(jobId: string): Promise<void> {
    if (!token) return;
    
    await fetch(API_BASE + `jobs/${jobId}/cancel`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` }
    });
    refreshJobs();
  }

  async function deleteImage(imageId: string): Promise<void> {
    if (!token) return;
    
    const res = await fetch(API_BASE + `images/${imageId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` }
    });
    
    if (res.ok) {
      setImages(images.filter(img => img.id !== imageId));
    }
  }

  async function toggleLike(imageId: string): Promise<void> {
    if (!token) return;
    
    const res = await fetch(API_BASE + `images/${imageId}/like`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` }
    });
    
    if (res.ok) {
      const result = await res.json();
      setImages(images.map(img => 
        img.id === imageId 
          ? { ...img, likes_count: result.likes_count, liked_by_user: result.liked }
          : img
      ));
    }
  }

  // Polling effect - only poll when needed
  useEffect(() => {
    if (!token) return;
    
    const intervals: NodeJS.Timeout[] = [];
    
    if (activePolling.jobs) {
      intervals.push(setInterval(refreshJobs, 5000));
    }
    if (activePolling.images) {
      intervals.push(setInterval(() => refreshImages(0, promptFilter), 10000));
    }
    if (activePolling.queue) {
      intervals.push(setInterval(refreshQueue, 5000));
    }
    
    return () => intervals.forEach(clearInterval);
  }, [token, activePolling]);

  // Initial data fetch
  useEffect(() => {
    if (token) {
      refreshJobs();
      refreshImages(0, promptFilter);
      refreshQueue();
    }
  }, [token]);

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString() + ' ' + new Date(dateString).toLocaleTimeString();
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'bg-green-500';
      case 'processing': return 'bg-blue-500';
      case 'queued': return 'bg-yellow-500';
      case 'failed': return 'bg-red-500';
      default: return 'bg-gray-500';
    }
  };

  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Card className="p-6 w-96">
          <CardHeader>
            <CardTitle className="text-2xl font-bold text-center">Welcome Back</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Input 
              placeholder="Username" 
              value={username} 
              onChange={e => setUsername(e.target.value)} 
            />
            <Input 
              type="password" 
              placeholder="Password" 
              value={password} 
              onChange={e => setPassword(e.target.value)} 
              onKeyDown={e => e.key === 'Enter' && login()}
            />
            <Button onClick={login} className="w-full">Sign In</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b bg-card">
        <div className="container mx-auto px-4 py-4 flex justify-between items-center">
          <h1 className="text-2xl font-bold">UnstableFusion</h1>
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <Sun className="h-4 w-4" />
              <Switch checked={isDarkMode} onCheckedChange={toggleDarkMode} />
              <Moon className="h-4 w-4" />
            </div>
            <Button variant="outline" onClick={() => setToken(null)}>
              Sign Out
            </Button>
          </div>
        </div>
      </div>

      <div className="container mx-auto p-4">
        <Tabs defaultValue="jobs" className="space-y-4">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="jobs">Jobs & Generate</TabsTrigger>
            <TabsTrigger value="images">Gallery</TabsTrigger>
            <TabsTrigger value="queue">Queue Status</TabsTrigger>
          </TabsList>

          <TabsContent value="jobs" className="space-y-6">
            {/* New Job Form */}
            <Card>
              <CardHeader>
                <CardTitle>Generate New Image</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <Input 
                  placeholder="Enter your prompt..." 
                  value={prompt} 
                  onChange={e => setPrompt(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && !isSubmittingJob && submitJob()}
                />
                <Select value={model} onValueChange={setModel}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select model" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="stabilityai/sd-turbo">stabilityai/sd-turbo</SelectItem>
                    <SelectItem value="stable-diffusion-v1-5/stable-diffusion-v1-5">stable-diffusion-v1-5/stable-diffusion-v1-5</SelectItem>
                    <SelectItem value="CompVis/stable-diffusion-v1-4">CompVis/stable-diffusion-v1-4</SelectItem>
                  </SelectContent>
                </Select>
                
                {/* Generation Parameters */}
                <div className="grid grid-cols-3 gap-4">
                  <div className="space-y-2">
                    <label className="text-sm font-medium">Width</label>
                    <Input 
                      type="number" 
                      value={width} 
                      onChange={e => setWidth(parseInt(e.target.value) || 256)}
                      min="64"
                      max="1024"
                      step="64"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium">Height</label>
                    <Input 
                      type="number" 
                      value={height} 
                      onChange={e => setHeight(parseInt(e.target.value) || 256)}
                      min="64"
                      max="1024"
                      step="64"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium">Steps</label>
                    <Input 
                      type="number" 
                      value={steps} 
                      onChange={e => setSteps(parseInt(e.target.value) || 20)}
                      min="1"
                      max="100"
                      step="1"
                    />
                  </div>
                </div>
                <Button 
                  onClick={submitJob} 
                  disabled={!prompt.trim() || isSubmittingJob}
                  className="w-full"
                >
                  {isSubmittingJob ? "Generating..." : "Generate Image"}
                </Button>
              </CardContent>
            </Card>

            <Separator />

            {/* Jobs List */}
            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <h2 className="text-xl font-semibold">My Jobs</h2>
                <Button 
                  variant="outline" 
                  size="sm" 
                  onClick={() => {
                    refreshJobs();
                    setActivePolling(prev => ({ ...prev, jobs: true }));
                  }}
                >
                  Refresh
                </Button>
              </div>
              
              {jobs.length === 0 ? (
                <Alert>
                  <AlertDescription>No jobs yet. Create your first image above!</AlertDescription>
                </Alert>
              ) : (
                jobs.map((job: Job) => (
                  <Card key={job.id}>
                    <CardContent className="pt-6">
                      <div className="flex justify-between items-start space-x-4">
                        <div className="flex-1 space-y-2">
                          <div className="flex items-center space-x-2">
                            <Badge className={getStatusColor(job.status)}>{job.status}</Badge>
                            <span className="text-sm text-muted-foreground flex items-center">
                              <Calendar className="h-4 w-4 mr-1" />
                              {formatDate(job.created_at)}
                            </span>
                          </div>
                          <p className="font-medium">{job.prompt}</p>
                          <p className="text-sm text-muted-foreground">Model: {job.model_name}</p>
                          <p className="text-sm text-muted-foreground">ID: {job.id}</p>
                        </div>
                        <div className="flex space-x-2">
                          {job.output_path && (
                            <Button 
                              variant="outline" 
                              size="sm"
                              onClick={() => downloadImage(job.id, token!)}
                            >
                              <Download className="h-4 w-4 mr-1" />
                              Download
                            </Button>
                          )}
                          {(job.status === 'queued' || job.status === 'processing') && (
                            <Button 
                              variant="destructive" 
                              size="sm"
                              onClick={() => cancelJob(job.id)}
                            >
                              <X className="h-4 w-4 mr-1" />
                              Cancel
                            </Button>
                          )}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))
              )}
            </div>
          </TabsContent>

          <TabsContent value="images" className="space-y-4">
            <div className="flex flex-col sm:flex-row gap-4 sm:items-center sm:justify-between">
              <h2 className="text-xl font-semibold">Image Gallery</h2>
              <div className="flex gap-2">
                <Input
                  placeholder="Filter by prompt..."
                  value={promptFilter}
                  onChange={e => setPromptFilter(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter') {
                      setImagesPage(0);
                      refreshImages(0, promptFilter);
                    }
                  }}
                  className="w-48"
                />
                <Button 
                  variant="outline" 
                  size="sm" 
                  onClick={() => {
                    setImagesPage(0);
                    refreshImages(0, promptFilter);
                    setActivePolling(prev => ({ ...prev, images: true }));
                  }}
                >
                  Refresh
                </Button>
              </div>
            </div>
            
            {images.length === 0 ? (
              <Alert>
                <AlertDescription>No images yet. Generate some images in the Jobs tab!</AlertDescription>
              </Alert>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                {images.map((img: Image) => (
                  <Card key={img.id} className="overflow-hidden hover:shadow-lg transition-shadow">
                    <div className="aspect-square relative group">
                      <img 
                        src={getAuthenticatedImageUrl(img.id, token!)}
                        alt={img.prompt} 
                        className="w-full h-full object-cover"
                        loading="lazy"
                      />
                      <div className="absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-30 transition-all duration-200 flex items-center justify-center opacity-0 group-hover:opacity-100">
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => downloadImage(img.id, token!)}
                        >
                          <Eye className="h-4 w-4 mr-1" />
                          View Full
                        </Button>
                      </div>
                    </div>
                    <CardContent className="p-4 space-y-3">
                      <p className="text-sm line-clamp-2 font-medium">{img.prompt}</p>
                      <p className="text-xs text-muted-foreground">Model: {img.model_name}</p>
                      <div className="flex justify-between items-center">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => toggleLike(img.id)}
                          className="flex items-center space-x-1 hover:text-red-500"
                        >
                          <Heart 
                            className={`h-4 w-4 ${img.liked_by_user ? 'fill-red-500 text-red-500' : ''}`} 
                          />
                          <span>{img.likes_count}</span>
                        </Button>
                        <div className="flex space-x-1">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => downloadImage(img.id, token!)}
                          >
                            <Download className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="destructive"
                            size="sm"
                            onClick={() => deleteImage(img.id)}
                          >
                            <X className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                      <p className="text-xs text-muted-foreground flex items-center">
                        <Calendar className="h-3 w-3 mr-1" />
                        {formatDate(img.created_at)}
                      </p>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
            
            {/* Pagination Controls */}
            {images.length > 0 && (
              <div className="flex justify-center items-center space-x-2 mt-6">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={imagesPage === 0}
                  onClick={() => {
                    const newPage = Math.max(0, imagesPage - 1);
                    setImagesPage(newPage);
                    refreshImages(newPage, promptFilter);
                  }}
                >
                  Previous
                </Button>
                <span className="text-sm text-muted-foreground">
                  Page {imagesPage + 1}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!hasMoreImages}
                  onClick={() => {
                    const newPage = imagesPage + 1;
                    setImagesPage(newPage);
                    refreshImages(newPage, promptFilter);
                  }}
                >
                  Next
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    const newPage = imagesPage + 1;
                    setImagesPage(newPage);
                    refreshImages(newPage, promptFilter, true);
                  }}
                  disabled={!hasMoreImages}
                >
                  Load More
                </Button>
              </div>
            )}
          </TabsContent>

          <TabsContent value="queue" className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-xl font-semibold">Queue Status</h2>
              <Button 
                variant="outline" 
                size="sm" 
                onClick={() => {
                  refreshQueue();
                  setActivePolling(prev => ({ ...prev, queue: true }));
                }}
              >
                Refresh
              </Button>
            </div>
            
            {queue && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Queue Statistics</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <div className="flex justify-between">
                      <span>Concurrency Limit:</span>
                      <Badge variant="secondary">{queue.concurrency_limit}</Badge>
                    </div>
                    <div className="flex justify-between">
                      <span>In Use:</span>
                      <Badge variant="secondary">{queue.in_use}</Badge>
                    </div>
                    <div className="flex justify-between">
                      <span>Queued Jobs:</span>
                      <Badge variant="secondary">{queue.queued}</Badge>
                    </div>
                    <div className="flex justify-between">
                      <span>Processing Jobs:</span>
                      <Badge variant="secondary">{queue.processing}</Badge>
                    </div>
                    <div className="flex justify-between">
                      <span>Completed Jobs:</span>
                      <Badge variant="secondary">{queue.done}</Badge>
                    </div>
                  </CardContent>
                </Card>
                
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Next Jobs</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {queue.next_jobs && queue.next_jobs.length > 0 ? (
                      <div className="space-y-3">
                        {queue.next_jobs.slice(0, 3).map((job, index) => (
                          <div key={job.id} className="text-sm space-y-1">
                            <div>
                              <span className="font-medium">{index + 1}.</span> {job.prompt.substring(0, 50)}...
                            </div>
                            <div className="text-xs text-muted-foreground">
                              {job.model_name} • {formatDate(job.created_at)}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground">No jobs in queue</p>
                    )}
                  </CardContent>
                </Card>
              </div>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}