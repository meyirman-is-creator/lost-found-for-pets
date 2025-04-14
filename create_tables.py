from app.db.database import engine, Base
from app.models.models import User, Pet, PetPhoto, PetMatch, Notification, VerificationCode

def create_tables():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")

if __name__ == "__main__":
    create_tables()