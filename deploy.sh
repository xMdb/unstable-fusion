#!/bin/bash

# UnstableFusion Unified Deployment Script
# This script consolidates all deployment operations for the UnstableFusion project
# It handles AWS infrastructure, configuration, and application deployment

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
TERRAFORM_DIR="terraform"
AWS_REGION="${AWS_REGION:-ap-southeast-2}"
USERNAME="${AWS_USERNAME:-n11974796}"

# Print functions
print_header() {
    echo -e "${BLUE}=================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}=================================${NC}"
}

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Show usage information
show_usage() {
    echo "UnstableFusion Unified Deployment Script"
    echo ""
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  deploy         - Full deployment (infrastructure + secrets + test)"
    echo "  infrastructure - Deploy only Terraform infrastructure"
    echo "  config         - Update AWS configuration and secrets"
    echo "  test           - Test AWS services connectivity"
    echo "  outputs        - Show Terraform outputs and set environment variables"
    echo "  clean          - Destroy all infrastructure"
    echo "  docker         - Build and run Docker containers"
    echo "  help           - Show this help message"
    echo ""
    echo "Options:"
    echo "  --region REGION    - AWS region (default: ap-southeast-2)"
    echo "  --username USER    - Username prefix for resources (default: unstablefusion)"
    echo "  --skip-confirm     - Skip confirmation prompts"
    echo ""
    echo "Examples:"
    echo "  $0 deploy                    # Full deployment with prompts"
    echo "  $0 deploy --region us-east-1 # Deploy in specific region"
    echo "  $0 test                      # Test configuration"
    echo "  $0 clean --skip-confirm      # Destroy without confirmation"
    echo ""
}

# Parse command line arguments
parse_arguments() {
    SKIP_CONFIRM=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --region)
                AWS_REGION="$2"
                shift 2
                ;;
            --username)
                USERNAME="$2"
                shift 2
                ;;
            --skip-confirm)
                SKIP_CONFIRM=true
                shift
                ;;
            *)
                break
                ;;
        esac
    done
}

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    local missing_tools=()
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        missing_tools+=("AWS CLI")
    fi
    
    # Check Terraform
    if ! command -v terraform &> /dev/null; then
        missing_tools+=("Terraform")
    fi
    
    # Check Docker (optional for some commands)
    if ! command -v docker &> /dev/null; then
        print_warning "Docker not found - some features may not work"
    fi
    
    if [ ${#missing_tools[@]} -ne 0 ]; then
        print_error "Missing required tools: ${missing_tools[*]}"
        echo ""
        echo "Please install the missing tools:"
        echo "- AWS CLI: https://aws.amazon.com/cli/"
        echo "- Terraform: https://www.terraform.io/downloads.html"
        echo "- Docker: https://www.docker.com/get-started"
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        print_error "AWS credentials not configured. Run 'aws configure' first."
        exit 1
    fi
    
    print_success "Prerequisites met"
}

# Confirm action with user
confirm_action() {
    local message="$1"
    local default="${2:-N}"
    
    if [ "$SKIP_CONFIRM" = true ]; then
        return 0
    fi
    
    if [ "$default" = "Y" ]; then
        echo -e "${YELLOW}$message (Y/n)?${NC}"
    else
        echo -e "${YELLOW}$message (y/N)?${NC}"
    fi
    
    read -r response
    
    if [ "$default" = "Y" ]; then
        [[ "$response" =~ ^[Nn]$ ]] && return 1 || return 0
    else
        [[ "$response" =~ ^[Yy]$ ]] && return 0 || return 1
    fi
}

# Deploy Terraform infrastructure
deploy_infrastructure() {
    print_header "Deploying Terraform Infrastructure"
    
    if [ ! -d "$TERRAFORM_DIR" ]; then
        print_error "Terraform directory not found: $TERRAFORM_DIR"
        exit 1
    fi
    
    cd "$TERRAFORM_DIR"
    
    # Initialize Terraform
    print_status "Initializing Terraform..."
    terraform init
    
    # Plan deployment
    print_status "Planning deployment..."
    terraform plan -out=tfplan
    
    # Ask for confirmation
    if confirm_action "Apply this Terraform plan?" "Y"; then
        print_status "Applying Terraform configuration..."
        terraform apply tfplan
        print_success "Infrastructure deployed successfully"
    else
        print_warning "Deployment cancelled"
        rm -f tfplan
        cd ..
        exit 0
    fi
    
    # Clean up plan file
    rm -f tfplan
    cd ..
}

# Update AWS configuration and secrets
update_configuration() {
    print_header "Updating AWS Configuration and Secrets"
    
    # Update Parameter Store parameters
    print_status "Updating Parameter Store parameters..."
    
    # Set basic parameters
    aws ssm put-parameter \
        --region "$AWS_REGION" \
        --name "/unstablefusion/$USERNAME/api_base_url" \
        --value "http://localhost:3001/api/" \
        --type "String" \
        --overwrite || true
    
    aws ssm put-parameter \
        --region "$AWS_REGION" \
        --name "/unstablefusion/$USERNAME/frontend_url" \
        --value "http://localhost:5173" \
        --type "String" \
        --overwrite || true
    
    aws ssm put-parameter \
        --region "$AWS_REGION" \
        --name "/unstablefusion/$USERNAME/default_model" \
        --value "CompVis/stable-diffusion-v1-4" \
        --type "String" \
        --overwrite || true
    
    # Update secrets
    print_status "Updating Secrets Manager secrets..."
    
    # Get Hugging Face token
    if confirm_action "Do you want to update the Hugging Face API token?"; then
        echo -e "${BLUE}Enter your Hugging Face API token (or press Enter to skip):${NC}"
        read -r -s HF_TOKEN
        
        if [ -n "$HF_TOKEN" ]; then
            print_status "Updating Hugging Face token..."
            aws secretsmanager update-secret \
                --region "$AWS_REGION" \
                --secret-id "unstablefusion/$USERNAME/huggingface-token" \
                --secret-string "{\"token\":\"$HF_TOKEN\",\"api_url\":\"https://api-inference.huggingface.co\",\"provider\":\"huggingface\"}" || \
            aws secretsmanager create-secret \
                --region "$AWS_REGION" \
                --name "unstablefusion/$USERNAME/huggingface-token" \
                --secret-string "{\"token\":\"$HF_TOKEN\",\"api_url\":\"https://api-inference.huggingface.co\",\"provider\":\"huggingface\"}"
            print_success "Hugging Face token updated"
        fi
    fi
    
    # Get Google OAuth credentials
    if confirm_action "Do you want to update Google OAuth credentials?"; then
        echo -e "${BLUE}Enter your Google OAuth client ID (or press Enter to skip):${NC}"
        read -r GOOGLE_CLIENT_ID
        
        if [ -n "$GOOGLE_CLIENT_ID" ]; then
            echo -e "${BLUE}Enter your Google OAuth client secret:${NC}"
            read -r -s GOOGLE_CLIENT_SECRET
            
            print_status "Updating Google OAuth credentials..."
            aws secretsmanager update-secret \
                --region "$AWS_REGION" \
                --secret-id "unstablefusion/$USERNAME/google-oauth-secret" \
                --secret-string "{\"client_id\":\"$GOOGLE_CLIENT_ID\",\"client_secret\":\"$GOOGLE_CLIENT_SECRET\",\"provider\":\"google\",\"scopes\":[\"openid\",\"email\",\"profile\"]}" || \
            aws secretsmanager create-secret \
                --region "$AWS_REGION" \
                --name "unstablefusion/$USERNAME/google-oauth-secret" \
                --secret-string "{\"client_id\":\"$GOOGLE_CLIENT_ID\",\"client_secret\":\"$GOOGLE_CLIENT_SECRET\",\"provider\":\"google\",\"scopes\":[\"openid\",\"email\",\"profile\"]}"
            print_success "Google OAuth credentials updated"
        fi
    fi
    
    # Generate and store JWT secret if not exists
    JWT_SECRET=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || echo "please-change-this-jwt-secret-$(date +%s)")
    aws secretsmanager update-secret \
        --region "$AWS_REGION" \
        --secret-id "unstablefusion/$USERNAME/jwt-secret" \
        --secret-string "{\"secret\":\"$JWT_SECRET\",\"algorithm\":\"HS256\",\"expiry_hours\":6}" 2>/dev/null || \
    aws secretsmanager create-secret \
        --region "$AWS_REGION" \
        --name "unstablefusion/$USERNAME/jwt-secret" \
        --secret-string "{\"secret\":\"$JWT_SECRET\",\"algorithm\":\"HS256\",\"expiry_hours\":6}"
    
    print_success "Configuration updated successfully"
}

# Test AWS services connectivity
test_configuration() {
    print_header "Testing AWS Services Connectivity"
    
    local test_failed=false
    
    # Test Parameter Store access
    print_status "Testing Parameter Store access..."
    if aws ssm get-parameters-by-path \
        --region "$AWS_REGION" \
        --path "/unstablefusion/$USERNAME" \
        --recursive > /dev/null 2>&1; then
        print_success "Parameter Store access working"
    else
        print_error "Parameter Store access failed"
        test_failed=true
    fi
    
    # Test Secrets Manager access
    print_status "Testing Secrets Manager access..."
    if aws secretsmanager list-secrets \
        --region "$AWS_REGION" \
        --filters Key=name,Values="unstablefusion/$USERNAME" > /dev/null 2>&1; then
        print_success "Secrets Manager access working"
    else
        print_error "Secrets Manager access failed"
        test_failed=true
    fi
    
    # Test Python AWS integration
    if command -v python3 &> /dev/null && [ -f "aws_config_service.py" ]; then
        print_status "Testing Python AWS integration..."
        if python3 -c "
import os
os.environ['AWS_REGION'] = '$AWS_REGION'
os.environ['AWS_USERNAME'] = '$USERNAME'
from aws_config_service import get_config_service
config = get_config_service()
print('✓ AWS Config Service working')
" 2>/dev/null; then
            print_success "Python AWS integration working"
        else
            print_warning "Python AWS integration test failed (this may be normal if dependencies aren't installed)"
        fi
    fi
    
    if [ "$test_failed" = true ]; then
        print_error "Some tests failed. Check your AWS configuration and permissions."
        return 1
    else
        print_success "All tests passed!"
        return 0
    fi
}

# Get and display Terraform outputs
show_outputs() {
    print_header "Terraform Outputs and Environment Variables"
    
    if [ ! -d "$TERRAFORM_DIR" ]; then
        print_error "Terraform directory not found: $TERRAFORM_DIR"
        return 1
    fi
    
    cd "$TERRAFORM_DIR"
    
    # Check if Terraform state exists
    if [ ! -f "terraform.tfstate" ]; then
        print_error "Terraform state not found. Please run infrastructure deployment first."
        cd ..
        return 1
    fi
    
    print_status "Getting Terraform outputs..."
    
    # Show structured outputs if available
    if terraform output > /dev/null 2>&1; then
        echo -e "${GREEN}Terraform Outputs:${NC}"
        terraform output 2>/dev/null || echo "No outputs available"
    fi
    
    echo ""
    echo -e "${GREEN}Environment Variables to Set:${NC}"
    echo "export AWS_REGION=\"$AWS_REGION\""
    echo "export AWS_USERNAME=\"$USERNAME\""
    
    # Try to get specific outputs
    local outputs=(
        "s3_bucket_name:AWS_S3_BUCKET"
        "database_url:DATABASE_URL"
        "cognito_user_pool_id:COGNITO_USER_POOL_ID"
        "cognito_app_client_id:COGNITO_APP_CLIENT_ID"
    )
    
    for output_pair in "${outputs[@]}"; do
        local tf_output="${output_pair%:*}"
        local env_var="${output_pair#*:}"
        local value
        value=$(terraform output -raw "$tf_output" 2>/dev/null)
        if [ $? -eq 0 ] && [ -n "$value" ]; then
            echo "export $env_var=\"$value\""
        fi
    done
    
    echo ""
    echo -e "${BLUE}To use these in your current shell, run:${NC}"
    echo "source <($0 outputs)"
    
    cd ..
}

# Build and run Docker containers
docker_deployment() {
    print_header "Docker Deployment"
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker not found. Please install Docker first."
        return 1
    fi
    
    if [ ! -f "compose.yml" ] && [ ! -f "docker-compose.yml" ]; then
        print_error "Docker Compose file not found (compose.yml or docker-compose.yml)"
        return 1
    fi
    
    local compose_file="compose.yml"
    [ -f "docker-compose.yml" ] && compose_file="docker-compose.yml"
    
    print_status "Building and starting Docker containers..."
    
    # Set environment variables for Docker
    export AWS_REGION="$AWS_REGION"
    export AWS_USERNAME="n11974796"
    
    # Build and start containers
    if docker compose -f "$compose_file" up --build -d; then
        print_success "Docker containers started successfully"
        echo ""
        echo -e "${GREEN}Application URLs:${NC}"
        echo "Frontend: http://localhost:3001"
        echo "API Documentation: http://localhost:3001/docs"
        echo ""
        echo -e "${BLUE}Default Users:${NC}"
        echo "Admin: username=admin, password=admin"
        echo "Demo: username=demo, password=demo"
        echo ""
        echo "To view logs: docker compose -f $compose_file logs -f"
        echo "To stop: docker compose -f $compose_file down"
    else
        print_error "Failed to start Docker containers"
        return 1
    fi
}

# Clean up infrastructure
cleanup_infrastructure() {
    print_header "Cleaning Up Infrastructure"
    
    if ! confirm_action "This will DESTROY all AWS infrastructure. Are you sure?" "N"; then
        print_warning "Cleanup cancelled"
        return 0
    fi
    
    if [ ! -d "$TERRAFORM_DIR" ]; then
        print_error "Terraform directory not found: $TERRAFORM_DIR"
        return 1
    fi
    
    cd "$TERRAFORM_DIR"
    
    print_status "Destroying Terraform infrastructure..."
    terraform destroy -auto-approve -var="aws_region=$AWS_REGION"
    
    print_success "Infrastructure destroyed"
    cd ..
}

# Main execution function
main() {
    local command="${1:-help}"
    
    # Parse arguments first
    parse_arguments "${@:2}"
    
    print_header "UnstableFusion Deployment - $command"
    echo "Region: $AWS_REGION"
    echo "Username: $USERNAME"
    echo ""
    
    case "$command" in
        "deploy")
            check_prerequisites
            deploy_infrastructure
            update_configuration
            test_configuration
            show_outputs
            echo ""
            print_success "Full deployment completed!"
            echo ""
            echo -e "${BLUE}Next Steps:${NC}"
            echo "1. Set environment variables (see outputs above)"
            echo "2. Run: $0 docker  # to start the application"
            ;;
        "infrastructure")
            check_prerequisites
            deploy_infrastructure
            ;;
        "config")
            check_prerequisites
            update_configuration
            ;;
        "test")
            check_prerequisites
            test_configuration
            ;;
        "outputs")
            show_outputs
            ;;
        "docker")
            docker_deployment
            ;;
        "clean")
            check_prerequisites
            cleanup_infrastructure
            ;;
        "help"|*)
            show_usage
            ;;
    esac
}

# Cleanup function for script exit
cleanup() {
    # Clean up any temporary files
    [ -f "$TERRAFORM_DIR/tfplan" ] && rm -f "$TERRAFORM_DIR/tfplan"
}

# Set trap for cleanup
trap cleanup EXIT

# Run main function with all arguments
main "$@"