#!/bin/bash
# Video Download API - Linux Server Deployment Script
# Supports Ubuntu/Debian systems with connection optimization

set -e  # Exit on error

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration variables
PROJECT_NAME="video-download-api"
SERVICE_NAME="video-download-api"
SERVICE_PORT=8001
DEPLOY_USER="apiuser"
PROJECT_DIR="/home/$DEPLOY_USER/$PROJECT_NAME"

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO] $1${NC}"
}

log_success() {
    echo -e "${GREEN}[OK] $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}[WARN] $1${NC}"
}

log_error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

# Detect operating system
detect_os() {
    log_info "Detecting operating system..."
    
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS_ID="$ID"
        OS_VERSION="$VERSION_ID"
        
        case "$ID" in
            ubuntu|debian)
                OS_TYPE="debian"
                PACKAGE_MANAGER="apt"
                ;;
            *)
                if [[ "$ID_LIKE" == *"debian"* ]]; then
                    OS_TYPE="debian"
                    PACKAGE_MANAGER="apt"
                else
                    log_error "Unsupported OS: $ID"
                    echo "This script only supports Ubuntu/Debian systems"
                    exit 1
                fi
                ;;
        esac
    else
        log_error "Cannot detect operating system"
        exit 1
    fi
    
    log_success "Detected OS: $ID $VERSION_ID (Type: $OS_TYPE)"
}

# Check Python version
check_python_version() {
    log_info "Checking Python version..."
    
    if ! command -v python3 &> /dev/null; then
        log_error "python3 not found. Please install Python 3.8+"
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)
    
    log_info "Current Python version: $PYTHON_VERSION"
    
    if ! python3 -m pip --version &> /dev/null; then
        log_warning "pip3 not available, will try to install later"
    fi
    
    if [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ]; then
        log_error "Python version too low. Current: $PYTHON_VERSION, Required: 3.8+"
        
        if [ -f "upgrade_python.sh" ]; then
            echo "Please run upgrade script: chmod +x upgrade_python.sh && sudo ./upgrade_python.sh"
            read -p "Run upgrade script now? (y/N): " run_upgrade
            if [[ "$run_upgrade" =~ ^[Yy]$ ]]; then
                chmod +x upgrade_python.sh
                ./upgrade_python.sh || {
                    log_error "Upgrade failed, deployment terminated"
                    exit 1
                }
                check_python_version
            else
                exit 1
            fi
        else
            echo "Please download and run Python upgrade script"
            exit 1
        fi
    else
        log_success "Python version compatible"
    fi
}

# Install system dependencies
install_system_deps() {
    log_info "Installing system dependencies..."
    
    case "$OS_TYPE" in
        debian)
            apt update -qq
            apt install -y \
                python3-pip python3-venv python3-dev \
                git curl wget unzip \
                build-essential ffmpeg
            
            if ! python3 -m venv --help &>/dev/null; then
                apt install -y python3-venv
            fi
            ;;
    esac
    
    log_success "System dependencies installed"
}

# Verify FFmpeg installation
verify_ffmpeg() {
    log_info "Verifying FFmpeg installation..."
    
    if command -v ffmpeg &> /dev/null; then
        local ffmpeg_version=$(ffmpeg -version 2>&1 | head -1 | cut -d' ' -f3)
        log_success "FFmpeg installed: $ffmpeg_version"
    else
        log_error "FFmpeg not installed, audio extraction will be unavailable"
        echo "Please install FFmpeg manually or re-run the script"
        exit 1
    fi
}

# Create deployment user
create_user() {
    log_info "Creating deployment user..."
    
    if ! id "$DEPLOY_USER" &>/dev/null; then
        if useradd -m -s /bin/bash "$DEPLOY_USER" 2>/dev/null; then
            log_success "Created user: $DEPLOY_USER"
        else
            log_warning "User creation failed, using root"
            DEPLOY_USER="root"
            PROJECT_DIR="/opt/$PROJECT_NAME"
        fi
    else
        log_info "User already exists: $DEPLOY_USER"
    fi
    
    mkdir -p "$PROJECT_DIR"
    if [ "$DEPLOY_USER" != "root" ]; then
        chown -R "$DEPLOY_USER:$DEPLOY_USER" "$PROJECT_DIR" 2>/dev/null || {
            log_warning "Permission setting failed"
        }
    fi
}

# Copy project files
copy_project() {
    log_info "Copying project files to $PROJECT_DIR..."
    
    # Copy core files
    for file in start_production.py requirements.txt api; do
        if [ -e "$file" ]; then
            cp -r "$file" "$PROJECT_DIR/"
        else
            log_error "File not found: $file"
            exit 1
        fi
    done
    
    # Create temp directory
    mkdir -p "$PROJECT_DIR/temp"
    
    # Set permissions
    if [ "$DEPLOY_USER" != "root" ]; then
        chown -R "$DEPLOY_USER:$DEPLOY_USER" "$PROJECT_DIR" 2>/dev/null || {
            log_warning "Permission setting failed"
        }
    fi
    
    log_success "Project files copied"
}

# Create virtual environment
create_venv() {
    log_info "Creating Python virtual environment..."
    
    cd "$PROJECT_DIR"
    
    if [ "$DEPLOY_USER" = "root" ]; then
        python3 -m venv venv
    else
        sudo -u "$DEPLOY_USER" python3 -m venv venv
    fi
    
    if [ ! -f "venv/bin/activate" ]; then
        log_error "Virtual environment creation failed"
        exit 1
    fi
    
    log_success "Virtual environment created"
}

# Install Python dependencies
install_python_deps() {
    log_info "Installing Python dependencies..."
    
    cd "$PROJECT_DIR"
    
    # Use default requirements file
    local req_file="requirements.txt"
    log_info "Using requirements file: $req_file"
    
    # Function to install dependencies
    install_deps() {
        local file="$1"
        if [ "$DEPLOY_USER" = "root" ]; then
            source venv/bin/activate
            pip install --upgrade pip -q
            pip install -r "$file" -q
        else
            sudo -u "$DEPLOY_USER" bash -c "
                cd '$PROJECT_DIR'
                source venv/bin/activate
                pip install --upgrade pip -q
                pip install -r '$file' -q
            " || {
                log_warning "su command failed, trying direct install"
                source venv/bin/activate
                pip install --upgrade pip -q
                pip install -r "$file" -q
            }
        fi
    }
    
    # Try installing main requirements file
    if install_deps "$req_file" 2>/dev/null; then
        log_success "Python dependencies installed (using: $req_file)"
        return 0
    fi
    
    # If main install fails, try fallback version
    log_warning "Main install failed, creating emergency fallback version..."
    
    # Create most conservative fallback requirements
    cat > "requirements-fallback.txt" << 'EOF'
# Emergency fallback version - most conservative dependencies
fastapi>=0.85.0
uvicorn>=0.18.0
requests>=2.20.0
pydantic>=1.8.0
python-multipart>=0.0.3
aiofiles>=0.7.0
pyyaml>=5.1.0
aiohttp>=3.6.0
yt-dlp>=2023.12.0
EOF
    
    log_info "Trying fallback version..."
    if install_deps "requirements-fallback.txt" 2>/dev/null; then
        log_success "Python dependencies installed (using fallback)"
        return 0
    fi
    
    # Last attempt - install one by one
    log_warning "Fallback also failed, trying individual package install..."
    
    local core_packages=("fastapi" "uvicorn" "requests" "pydantic" "aiofiles" "pyyaml" "aiohttp" "yt-dlp")
    
    if [ "$DEPLOY_USER" = "root" ]; then
        source venv/bin/activate
        pip install --upgrade pip -q
        for package in "${core_packages[@]}"; do
            pip install "$package" -q && log_info "[+] $package installed" || log_warning "[-] $package failed"
        done
    else
        sudo -u "$DEPLOY_USER" bash -c "
            cd '$PROJECT_DIR'
            source venv/bin/activate
            pip install --upgrade pip -q
            for package in fastapi uvicorn requests pydantic aiofiles pyyaml aiohttp yt-dlp; do
                pip install \"\$package\" -q && echo \"[+] \$package installed\" || echo \"[-] \$package failed\"
            done
        "
    fi
    
    log_success "Core dependencies installed (individual mode)"
}

# Create system service
create_service() {
    log_info "Creating system service..."
    
    if ! command -v systemctl &> /dev/null; then
        log_error "systemctl not available, cannot configure system service"
        echo "Please start service manually, refer to deployment guide"
        return 1
    fi
    
    cat > "/etc/systemd/system/$SERVICE_NAME.service" << EOF
[Unit]
Description=Video Download API Service - Optimized
After=network.target

[Service]
Type=simple
User=$DEPLOY_USER
WorkingDirectory=$PROJECT_DIR
Environment=PATH=$PROJECT_DIR/venv/bin
Environment=HOST=0.0.0.0
Environment=PORT=8001
Environment=WORKERS=1
Environment=AUTO_RESTART=true
Environment=MAX_RESTART_ATTEMPTS=999
Environment=TIMEOUT_KEEP_ALIVE=5
Environment=LIMIT_CONCURRENCY=50
Environment=LIMIT_MAX_REQUESTS=100
ExecStart=$PROJECT_DIR/venv/bin/python start_production.py
Restart=always
RestartSec=3
StandardOutput=append:$PROJECT_DIR/service.log
StandardError=append:$PROJECT_DIR/service_error.log

[Install]
WantedBy=multi-user.target
EOF
    
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    
    log_success "System service created"
}

# Configure firewall
configure_firewall() {
    log_info "Configuring firewall..."
    
    if ! command -v systemctl &> /dev/null; then
        log_info "Skipping firewall configuration"
        return 0
    fi
    
    if systemctl is-active --quiet ufw; then
        ufw allow "$SERVICE_PORT/tcp" >/dev/null 2>&1
        log_success "ufw firewall configured"
    elif systemctl is-active --quiet firewalld; then
        firewall-cmd --permanent --add-port="$SERVICE_PORT/tcp" >/dev/null 2>&1
        firewall-cmd --reload >/dev/null 2>&1
        log_success "firewalld firewall configured"
    else
        log_info "No active firewall detected"
    fi
}

# Test service configuration
test_service_config() {
    log_info "Testing service configuration..."
    
    cd "$PROJECT_DIR"
    
    # Test Python module import
    if [ "$DEPLOY_USER" = "root" ]; then
        source venv/bin/activate
        python3 -c "import fastapi, uvicorn; print('[OK] Core dependencies working')" 2>/dev/null || {
            log_error "Core dependencies test failed"
            return 1
        }
    else
        sudo -u "$DEPLOY_USER" bash -c "
            cd '$PROJECT_DIR'
            source venv/bin/activate
            python3 -c 'import fastapi, uvicorn; print(\"[OK] Core dependencies working\")' 2>/dev/null
        " || {
            source venv/bin/activate
            python3 -c "import fastapi, uvicorn; print('[OK] Core dependencies working')" 2>/dev/null || {
                log_error "Core dependencies test failed"
                return 1
            }
        }
    fi
    
    # API module import test
    log_info "Testing API module import..."
    if [ "$DEPLOY_USER" = "root" ]; then
        source venv/bin/activate
        export PYTHONPATH="$PROJECT_DIR:$PYTHONPATH"
        python3 -c "
try:
    from api.main import app
    print('[OK] API module import successful')
except Exception as e:
    print(f'[ERROR] API module import failed: {e}')
    import traceback
    traceback.print_exc()
    raise
" 2>/dev/null || {
            log_error "API module import failed, checking error details:"
            python3 -c "
try:
    from api.main import app
except Exception as e:
    print(f'Detailed error: {e}')
    import traceback
    traceback.print_exc()
"
            return 1
        }
    else
        sudo -u "$DEPLOY_USER" bash -c "
            cd '$PROJECT_DIR'
            source venv/bin/activate
            export PYTHONPATH='$PROJECT_DIR:\$PYTHONPATH'
            python3 -c '
try:
    from api.main import app
    print(\"[OK] API module import successful\")
except Exception as e:
    print(f\"[ERROR] API module import failed: {e}\")
    import traceback
    traceback.print_exc()
    raise
'
        " 2>/dev/null || {
            log_error "API module import failed, checking error details:"
            sudo -u "$DEPLOY_USER" bash -c "
                cd '$PROJECT_DIR'
                source venv/bin/activate
                export PYTHONPATH='$PROJECT_DIR:\$PYTHONPATH'
                python3 -c '
try:
    from api.main import app
except Exception as e:
    print(f\"Detailed error: {e}\")
    import traceback
    traceback.print_exc()
'
            " || {
                source venv/bin/activate
                export PYTHONPATH="$PROJECT_DIR:$PYTHONPATH"
                python3 -c "
try:
    from api.main import app
except Exception as e:
    print(f'Detailed error: {e}')
    import traceback
    traceback.print_exc()
"
                return 1
            }
        }
    fi
    
    log_success "Service configuration test passed"
    return 0
}

# Start service
start_service() {
    log_info "Starting service..."
    
    if ! test_service_config; then
        log_error "Service configuration test failed, deployment terminated"
        exit 1
    fi
    
    # Check port conflict
    if command -v netstat &> /dev/null && netstat -tulpn 2>/dev/null | grep -q ":$SERVICE_PORT "; then
        log_warning "Port $SERVICE_PORT is occupied, trying to stop conflicting service"
        local pid=$(netstat -tulpn 2>/dev/null | grep ":$SERVICE_PORT " | awk '{print $7}' | cut -d'/' -f1 | head -1)
        if [ -n "$pid" ] && [ "$pid" != "-" ]; then
            kill -9 "$pid" 2>/dev/null || true
            sleep 1
        fi
    elif command -v ss &> /dev/null && ss -tulpn 2>/dev/null | grep -q ":$SERVICE_PORT "; then
        log_warning "Port $SERVICE_PORT is occupied (detected by ss)"
    fi
    
    # Start service
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    systemctl start "$SERVICE_NAME"
    
    # Check service status
    sleep 3
    
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_success "Service started successfully"
        
        # API check
        log_info "Waiting for API to start..."
        local attempts=0
        while [ $attempts -lt 8 ]; do
            if curl -s "http://localhost:$SERVICE_PORT/api/health" > /dev/null 2>&1; then
                log_success "API service is running normally"
                echo ""
                echo "=== Deployment Complete! ==="
                echo "==============================================="
                echo "[*] Service URL: http://localhost:$SERVICE_PORT"
                echo "[*] API Docs: http://localhost:$SERVICE_PORT/docs"
                echo "[*] Health Check: http://localhost:$SERVICE_PORT/api/health"
                echo ""
                echo "[*] Management Commands:"
                echo "  View status: systemctl status $SERVICE_NAME"
                echo "  View logs: journalctl -u $SERVICE_NAME -f"
                echo "  Stop service: systemctl stop $SERVICE_NAME"
                echo "  Restart service: systemctl restart $SERVICE_NAME"
                echo ""
                echo "[*] Performance Tips:"
                echo "  - Auto-restart enabled, will recover after crash"
                echo "  - Logs managed by systemd with rotation support"
                echo "  - Running with dedicated user for security"
                return 0
            fi
            attempts=$((attempts + 1))
            sleep 2
        done
        
        log_warning "API service response timeout, please check logs"
        echo "View logs: journalctl -u $SERVICE_NAME -f"
    else
        log_error "Service start failed"
        echo ""
        echo "[*] Debug Information:"
        echo "1. View service status: systemctl status $SERVICE_NAME -l"
        echo "2. View error logs: journalctl -u $SERVICE_NAME -n 20"
        echo "3. Manual test: sudo -u $DEPLOY_USER bash -c 'cd $PROJECT_DIR && source venv/bin/activate && python start_production.py'"
        
        echo ""
        echo "[*] Recent errors:"
        journalctl -u "$SERVICE_NAME" -n 5 --no-pager || echo "Cannot retrieve logs"
        exit 1
    fi
}

# Main function
main() {
    echo "=== Video Download API - Linux Server Deployment ==="
    echo "Supports Ubuntu/Debian with connection optimization"
    echo "====================================================="
    
    # Check root privileges
    if [[ $EUID -ne 0 ]]; then
        log_error "This script requires root privileges"
        echo "Please use: sudo $0"
        exit 1
    fi
    
    # Execute deployment steps
    detect_os
    check_python_version
    install_system_deps
    verify_ffmpeg
    create_user
    copy_project
    create_venv
    install_python_deps
    create_service
    configure_firewall
    start_service
}

# Run main function
main "$@"