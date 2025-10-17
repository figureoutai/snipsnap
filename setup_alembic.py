import os
import subprocess


def setup_alembic():
    """Initialize Alembic if not already initialized."""
    if not os.path.exists('alembic'):
        print("Initializing Alembic...")
        subprocess.run(['alembic', 'init', 'alembic'])
        print("✓ Alembic initialized")
        print("\nNext steps:")
        print("1. Update alembic.ini with your database URL")
        print("2. Replace alembic/env.py with the provided version")
        print("3. Add the migration file to alembic/versions/")
    else:
        print("Alembic already initialized")


def run_migrations():
    """Run all pending migrations."""
    print("\nRunning migrations...")
    result = subprocess.run(['alembic', 'upgrade', 'head'], capture_output=True, text=True)
    print(result.stdout)
    if result.returncode == 0:
        print("✓ Migrations completed successfully")
    else:
        print("✗ Migration failed:")
        print(result.stderr)


def create_migration(message):
    """Create a new migration."""
    print(f"\nCreating migration: {message}")
    result = subprocess.run(['alembic', 'revision', '--autogenerate', '-m', message], 
                          capture_output=True, text=True)
    print(result.stdout)
    if result.returncode == 0:
        print("✓ Migration created successfully")
    else:
        print("✗ Migration creation failed:")
        print(result.stderr)


def check_current_revision():
    """Check current database revision."""
    result = subprocess.run(['alembic', 'current'], capture_output=True, text=True)
    print("\nCurrent database revision:")
    print(result.stdout)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python setup_alembic.py init          # Initialize Alembic")
        print("  python setup_alembic.py migrate       # Run migrations")
        print("  python setup_alembic.py revision 'msg' # Create new migration")
        print("  python setup_alembic.py current       # Check current revision")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == 'init':
        setup_alembic()
    elif command == 'migrate':
        run_migrations()
    elif command == 'revision':
        if len(sys.argv) < 3:
            print("Please provide a migration message")
            sys.exit(1)
        create_migration(sys.argv[2])
    elif command == 'current':
        check_current_revision()
    else:
        print(f"Unknown command: {command}")