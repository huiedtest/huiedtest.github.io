from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    bookings = db.relationship('Booking', backref='room', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Room {self.name}>'

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    user_name = db.Column(db.String(120), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    details = db.Column(db.Text, nullable=True)
    start_time = db.Column(db.DateTime, nullable=False, index=True)
    end_time = db.Column(db.DateTime, nullable=False)

    def __repr__(self):
        return f'<Booking {self.title} by {self.user_name} in Room {self.room.name}>'

    @property
    def duration_minutes(self):
        return (self.end_time - self.start_time).total_seconds() / 60

    @property
    def start_hour_minute(self):
        return self.start_time.hour + self.start_time.minute / 60.0

    @property
    def end_hour_minute(self):
        end_hm = self.end_time.hour + self.end_time.minute / 60.0
        if end_hm == 0.0 and self.end_time.date() > self.start_time.date():
             return 24.0
        return end_hm