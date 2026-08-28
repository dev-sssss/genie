import os
from app.database import engine
from app.models import User
from app.auth import get_password_hash
from sqlalchemy.orm import sessionmaker

def seed_db():
    print("Seeding database...")
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Create an initial demo user
        demo_email = "admin@pipelinegenie.com"
        existing_user = db.query(User).filter(User.email == demo_email).first()
        
        if not existing_user:
            hashed_pwd = get_password_hash("genie123!")
            new_user = User(email=demo_email, hashed_password=hashed_pwd)
            db.add(new_user)
            db.commit()
            print(f"Seed user '{demo_email}' created successfully.")
        else:
            print(f"Seed user '{demo_email}' already exists. Skipping.")
    finally:
        db.close()
    
    print("Database seeding completed!")

if __name__ == "__main__":
    seed_db()
