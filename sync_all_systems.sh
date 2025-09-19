#!/bin/bash

# =============================================================================
# SRE Dashboard - Complete System Sync Script
# =============================================================================
# This script activates the Python environment and runs all sync commands
# for Sentry, JIRA, SonarCloud, and Dashboard refresh operations.
# =============================================================================

set -e  # Exit on any error

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="/home/asher/pyenv"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/sync_$(date +%Y%m%d_%H%M%S).log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}" | tee -a "$LOG_FILE"
}

# Function to print section headers
print_header() {
    local title=$1
    echo "" | tee -a "$LOG_FILE"
    echo "=============================================================" | tee -a "$LOG_FILE"
    print_status $CYAN "$title"
    echo "=============================================================" | tee -a "$LOG_FILE"
}

# Function to run command with logging
run_command() {
    local description=$1
    local command=$2
    local start_time=$(date +%s)
    
    print_status $YELLOW "▶ $description"
    echo "Command: $command" >> "$LOG_FILE"
    
    if eval "$command" >> "$LOG_FILE" 2>&1; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        print_status $GREEN "✅ $description completed in ${duration}s"
        return 0
    else
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        print_status $RED "❌ $description failed after ${duration}s"
        return 1
    fi
}

# Function to check if virtual environment exists
check_venv() {
    if [ ! -d "$VENV_PATH" ]; then
        print_status $RED "❌ Virtual environment not found at $VENV_PATH"
        print_status $YELLOW "Please update VENV_PATH in the script or create the virtual environment"
        exit 1
    fi
    
    if [ ! -f "$VENV_PATH/bin/activate" ]; then
        print_status $RED "❌ Virtual environment activation script not found"
        exit 1
    fi
}

# Function to activate virtual environment
activate_venv() {
    print_status $BLUE "🐍 Activating Python virtual environment..."
    source "$VENV_PATH/bin/activate"
    
    if [ "$VIRTUAL_ENV" != "$VENV_PATH" ]; then
        print_status $RED "❌ Failed to activate virtual environment"
        exit 1
    fi
    
    print_status $GREEN "✅ Virtual environment activated: $VIRTUAL_ENV"
    python --version | tee -a "$LOG_FILE"
}

# Function to check Django setup
check_django() {
    print_status $BLUE "🔍 Checking Django setup..."
    
    if ! run_command "Django system check" "python manage.py check"; then
        print_status $RED "❌ Django system check failed"
        exit 1
    fi
}

# Function to sync JIRA data
sync_jira() {
    print_header "🎫 JIRA SYNC"
    
    run_command "Syncing JIRA projects and issues" "python manage.py sync_jira"
}

# Function to sync SonarCloud data
sync_sonarcloud() {
    print_header "✅ SONARCLOUD SYNC"
    
    run_command "Syncing SonarCloud organizations and projects" "python manage.py sync_sonarcloud --force"
}

# Function to sync Azure data
sync_azure() {
    print_header "☁️ AZURE SYNC"
    
    run_command "Syncing Azure infrastructure and metrics" "python manage.py sync_azure --force"
}

# Function to sync Sentry data
sync_sentry() {
    print_header "🔥 SENTRY SYNC"
    
    run_command "Syncing Sentry organizations and projects" "python manage.py sync_sentry --force"
    run_command "Auto-linking Sentry issues to JIRA" "python manage.py sync_sentry --link-jira"
    run_command "Fuzzy matching Sentry issues with JIRA" "python manage.py sync_sentry --fuzzy-match"
}

# Function to refresh dashboard cache
refresh_dashboards() {
    print_header "📊 DASHBOARD REFRESH"
    
    run_command "Refreshing executive dashboard cache" "python manage.py refresh_dashboards --dashboard executive --force"
    run_command "Refreshing product dashboard cache" "python manage.py refresh_dashboards --dashboard product --force"
    run_command "Refreshing environment dashboard cache" "python manage.py refresh_dashboards --dashboard environment --force"
    run_command "Cleaning up expired dashboard snapshots" "python manage.py refresh_dashboards --cleanup"
}

# Function to show final statistics
show_statistics() {
    print_header "📈 SYNC STATISTICS"
    
    run_command "Dashboard cache statistics" "python manage.py refresh_dashboards --stats"
    
    print_status $PURPLE "📝 Full sync log saved to: $LOG_FILE"
}

# Function to handle cleanup on exit
cleanup() {
    if [ ! -z "$VIRTUAL_ENV" ]; then
        print_status $BLUE "🔄 Deactivating virtual environment..."
        deactivate 2>/dev/null || true
    fi
}

# Main execution function
main() {
    local start_time=$(date +%s)
    
    print_header "🚀 SRE DASHBOARD - COMPLETE SYSTEM SYNC"
    print_status $CYAN "Started at: $(date)"
    print_status $CYAN "Log file: $LOG_FILE"
    
    # Setup and checks
    check_venv
    activate_venv
    check_django
    
    # Parse command line arguments
    local sync_sentry=true
    local sync_jira=true
    local sync_sonarcloud=true
    local sync_azure=true
    local refresh_cache=true
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-sentry)
                sync_sentry=false
                print_status $YELLOW "⏩ Skipping Sentry sync"
                shift
                ;;
            --skip-jira)
                sync_jira=false
                print_status $YELLOW "⏩ Skipping JIRA sync"
                shift
                ;;
            --skip-sonarcloud)
                sync_sonarcloud=false
                print_status $YELLOW "⏩ Skipping SonarCloud sync"
                shift
                ;;
            --skip-azure)
                sync_azure=false
                print_status $YELLOW "⏩ Skipping Azure sync"
                shift
                ;;
            --skip-dashboards)
                refresh_cache=false
                print_status $YELLOW "⏩ Skipping dashboard refresh"
                shift
                ;;
            --only-dashboards)
                sync_sentry=false
                sync_jira=false
                sync_sonarcloud=false
                sync_azure=false
                print_status $YELLOW "🎯 Only refreshing dashboards"
                shift
                ;;
            --help|-h)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --skip-sentry      Skip Sentry sync"
                echo "  --skip-jira        Skip JIRA sync"
                echo "  --skip-sonarcloud  Skip SonarCloud sync"
                echo "  --skip-azure       Skip Azure sync"
                echo "  --skip-dashboards  Skip dashboard refresh"
                echo "  --only-dashboards  Only refresh dashboards"
                echo "  --help, -h         Show this help message"
                exit 0
                ;;
            *)
                print_status $RED "❌ Unknown option: $1"
                echo "Use --help for usage information"
                exit 1
                ;;
        esac
    done
    
    # Execute sync operations
    local failed_operations=0
    
    if [ "$sync_sentry" = true ]; then
        if ! sync_sentry; then
            ((failed_operations++))
        fi
    fi
    
    if [ "$sync_jira" = true ]; then
        if ! sync_jira; then
            ((failed_operations++))
        fi
    fi
    
    if [ "$sync_sonarcloud" = true ]; then
        if ! sync_sonarcloud; then
            ((failed_operations++))
        fi
    fi
    
    if [ "$sync_azure" = true ]; then
        if ! sync_azure; then
            ((failed_operations++))
        fi
    fi
    
    if [ "$refresh_cache" = true ]; then
        if ! refresh_dashboards; then
            ((failed_operations++))
        fi
    fi
    
    # Show final results
    show_statistics
    
    local end_time=$(date +%s)
    local total_duration=$((end_time - start_time))
    local minutes=$((total_duration / 60))
    local seconds=$((total_duration % 60))
    
    print_header "🏁 SYNC COMPLETED"
    print_status $CYAN "Completed at: $(date)"
    print_status $CYAN "Total duration: ${minutes}m ${seconds}s"
    
    if [ $failed_operations -eq 0 ]; then
        print_status $GREEN "🎉 All operations completed successfully!"
        exit 0
    else
        print_status $YELLOW "⚠️  $failed_operations operation(s) had issues - check the log for details"
        exit 1
    fi
}

# Set up cleanup trap
trap cleanup EXIT

# Run main function with all arguments
main "$@"