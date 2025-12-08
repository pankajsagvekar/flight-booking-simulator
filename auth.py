from fastapi import Request, Depends, HTTPException, status
from fastapi.responses import Response
from itsdangerous import URLSafeSerializer, BadSignature
from sqlalchemy.orm import Session

from database import SessionLocal
from models import User

# WARNING: This is a simplified and insecure authentication system.
# In a real application, you should use a secure session management system
# and never store passwords in plaintext.
SECRET_KEY = "a-very-secret-key-that-should-be-in-an-env-file"
serializer = URLSafeSerializer(SECRET_KEY)

def login_user(response: Response, user: User):
    """Sets a session cookie to log the user in."""
    session_data = serializer.dumps({"user_id": user.id})
    response.set_cookie(key="session", value=session_data, httponly=True)

def logout_user(response: Response):
    """Clears the session cookie to log the user out."""
    response.delete_cookie(key="session")

def get_current_user(request: Request, db: Session = Depends(SessionLocal)):
    """Dependency to get the current user from the session cookie."""
    session_cookie = request.cookies.get("session")
    if not session_cookie:
        return None

    try:
        session_data = serializer.loads(session_cookie)
        user_id = session_data.get("user_id")
        if not user_id:
            return None
        return db.query(User).filter(User.id == user_id).first()
    except BadSignature:
        return None

def create_initial_users():
    """Creates initial admin and user accounts if they don't exist."""
    db = SessionLocal()
    if db.query(User).count() == 0:
        print("Creating initial users...")
        admin_user = User(
            username="admin",
            email="admin@example.com",
            password="admin",  # WARNING: Plaintext password
            full_name="Admin User",
            role="admin",
        )
        db.add(admin_user)

        test_user = User(
            username="user",
            email="user@example.com",
            password="user",  # WARNING: Plaintext password
            full_name="Test User",
            role="user",
        )
        db.add(test_user)
        db.commit()
        print("Initial users created.")
    db.close()