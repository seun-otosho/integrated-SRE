#!/usr/bin/env python
"""
Setup script for the Sentry Management System

This script will:
1. Install dependencies
2. Run migrations
3. Create a superuser (if needed)
4. Provide setup instructions
"""

import os
import sys
import subprocess
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()

def run_command(command, description):
    """Run a shell command and handle errors"""
    print(f"\n🔄 {description}...")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed:")
        print(e.stderr)
        return False

def main():
    print("🚀 Setting up Sentry Management System")
    print("=" * 50)
    
    # Install dependencies
    if not run_command("pip install -r requirements.txt", "Installing dependencies"):
        print("⚠️ Failed to install dependencies. Please run: pip install -r requirements.txt")
    
    # Run migrations
    if not run_command("python manage.py makemigrations", "Creating migrations"):
        return False
    
    if not run_command("python manage.py migrate", "Running migrations"):
        return False
    
    # Check if superuser exists
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    if not User.objects.filter(is_superuser=True).exists():
        print("\n👤 No superuser found. Let's create one...")
        try:
            subprocess.run("python manage.py createsuperuser", shell=True, check=True)
        except subprocess.CalledProcessError:
            print("⚠️ Superuser creation cancelled or failed")
    
    print("\n🎉 Setup completed successfully!")
    print("\n" + "=" * 50)
    print("📋 NEXT STEPS:")
    print("=" * 50)
    
    print("\n1. 🔐 Get your Sentry API token:")
    print("   - Go to https://sentry.io/settings/account/api/auth-tokens/")
    print("   - Create a new token with 'org:read' and 'project:read' permissions")
    
    print("\n2. 🏢 Add your Sentry organization:")
    print("   - Start the development server: python manage.py runserver")
    print("   - Go to http://localhost:8000/admin/")
    print("   - Navigate to Sentry > Sentry Organizations")
    print("   - Click 'Add Sentry Organization' and fill in:")
    print("     * Name: Your organization name")
    print("     * Slug: Your organization slug (from Sentry URL)")
    print("     * API Token: The token you created")
    print("     * Sync Enabled: ✓ (checked)")
    print("     * Sync Interval Hours: 3 (or your preference)")
    
    print("\n3. 🔄 Set up periodic syncing:")
    print("   - Option A: Cron job (recommended)")
    print("     Add this to your crontab (crontab -e):")
    print("     0 */3 * * * /usr/bin/python3 /path/to/your/project/apps/sentry/cron.py")
    print("")
    print("   - Option B: Manual sync")
    print("     Run: python manage.py sync_sentry")
    print("")
    print("   - Option C: Django admin trigger")
    print("     Use the 'Sync Now' button in the admin interface")
    
    print("\n4. 📊 Access your data:")
    print("   - Dashboard: http://localhost:8000/sentry/")
    print("   - Admin Interface: http://localhost:8000/admin/sentry/")
    print("   - Wagtail Admin: http://localhost:8000/admin/")
    
    print("\n5. 🧪 Test the setup:")
    print("   - Go to the dashboard and click 'Test API Connection'")
    print("   - Or run: python manage.py sync_sentry --dry-run")
    
    print("\n" + "=" * 50)
    print("📚 USEFUL COMMANDS:")
    print("=" * 50)
    print("  python manage.py sync_sentry                    # Sync all organizations")
    print("  python manage.py sync_sentry --org myorg        # Sync specific org")
    print("  python manage.py sync_sentry --force            # Force sync even if recent")
    print("  python manage.py sync_sentry --dry-run          # Show what would be synced")
    print("")
    print("Happy monitoring! 🎯")

if __name__ == '__main__':
    main()