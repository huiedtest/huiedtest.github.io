from flask import Flask, render_template, request, redirect, url_for, flash, abort
from models import db, Room, Booking
from datetime import datetime, date, timedelta, time
import calendar
from dateutil.relativedelta import relativedelta
from sqlalchemy import distinct
from urllib.parse import unquote, quote

app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_strong_and_unique_secret_key' # CHANGE THIS!
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///meetings.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

MEETING_ROOM_NAMES = ["111111", "555555", "666666", "666888", "888888"]
VIEW_START_HOUR = 8
VIEW_END_HOUR = 22
HOURS_IN_VIEW = VIEW_END_HOUR - VIEW_START_HOUR
PIXELS_PER_HOUR = 60

def initialize_database():
    with app.app_context():
        db.create_all()
        if Room.query.count() == 0:
            for room_name in MEETING_ROOM_NAMES:
                db.session.add(Room(name=room_name))
            db.session.commit()
            print("Database initialized and rooms created.")
        else:
            print("Database already exists.")

def get_month_data(year, month):
    month_calendar = calendar.monthcalendar(year, month)
    current_dt = date(year, month, 1)
    prev_month = current_dt - relativedelta(months=1)
    next_month = current_dt + relativedelta(months=1)
    month_name = current_dt.strftime("%B %Y")
    return month_calendar, prev_month, next_month, month_name

def get_week_data(year, week_num):
    try:
        start_of_week = datetime.strptime(f'{year}-W{week_num:02d}-1', "%G-W%V-%u").date()
    except ValueError as e:
        print(f"Error parsing date: {e}. Input: year={year}, week_num={week_num}")
        raise ValueError(f"Invalid year/week combination: {year}-W{week_num}") from e
    end_of_week = start_of_week + timedelta(days=6)
    days_in_week = [(start_of_week + timedelta(days=i)) for i in range(7)]
    prev_week_dt = start_of_week - timedelta(weeks=1)
    next_week_dt = start_of_week + timedelta(weeks=1)
    prev_week_year, prev_week_num, _ = prev_week_dt.isocalendar()
    next_week_year, next_week_num, _ = next_week_dt.isocalendar()
    week_label = f"Week {week_num}, {year} ({start_of_week.strftime('%b %d')} - {end_of_week.strftime('%b %d')})"
    return start_of_week, end_of_week, days_in_week, prev_week_year, prev_week_num, next_week_year, next_week_num, week_label


def calculate_display_params(booking, day_date, view_start_hour, view_end_hour, pixels_per_hour=PIXELS_PER_HOUR):
    pixels_per_minute = pixels_per_hour / 60.0
    view_start_dt = datetime.combine(day_date, time(view_start_hour, 0))
    view_end_dt = datetime.combine(day_date, time(view_end_hour, 0))
    clamped_start = max(booking.start_time, view_start_dt)
    clamped_end = min(booking.end_time, view_end_dt)
    if clamped_end <= clamped_start or clamped_start >= view_end_dt or clamped_end <= view_start_dt:
        return None
    start_minute_offset = max(0, (clamped_start - view_start_dt).total_seconds() / 60)
    end_minute_offset = max(0, (clamped_end - view_start_dt).total_seconds() / 60)
    duration_minutes = end_minute_offset - start_minute_offset
    if duration_minutes <= 0:
        return None
    top_px = start_minute_offset * pixels_per_minute
    height_px = duration_minutes * pixels_per_minute
    return {
        'id': booking.id, 'title': booking.title, 'details': booking.details,
        'start_time_str': booking.start_time.strftime('%H:%M'),
        'end_time_str': booking.end_time.strftime('%H:%M'),
        'top': round(top_px, 2), 'height': round(height_px, 2)
    }

@app.context_processor
def inject_now():
    return {'now': datetime.now()}

@app.route('/')
@app.route('/month')
@app.route('/month/<int:year>/<int:month>')
def month_view(year=None, month=None):
    today = date.today()
    if year is None or month is None:
        year, month = today.year, today.month
    try:
        if not 1 <= month <= 12:
             raise ValueError("Invalid month")
        date(year, month, 1)
    except ValueError:
        flash("Invalid date requested.", "warning")
        year, month = today.year, today.month
    month_calendar, prev_month, next_month, month_name = get_month_data(year, month)
    return render_template('month.html',
                           calendar_data=month_calendar,
                           month_name=month_name,
                           current_year=year,
                           current_month=month,
                           prev_year=prev_month.year,
                           prev_month=prev_month.month,
                           next_year=next_month.year,
                           next_month=next_month.month,
                           today=today,
                           date=date)

@app.route('/day/<int:year>/<int:month>/<int:day>')
def day_view(year, month, day):
    try:
        current_date = date(year, month, day)
    except ValueError:
        flash("Invalid date requested.", "warning")
        return redirect(url_for('month_view'))
    rooms = Room.query.order_by(Room.name).all()
    view_day_start_dt = datetime.combine(current_date, time.min)
    view_day_end_dt = datetime.combine(current_date + timedelta(days=1), time.min)
    bookings_today = Booking.query.filter(
        Booking.start_time < view_day_end_dt,
        Booking.end_time > view_day_start_dt
    ).order_by(Booking.start_time).all()
    bookings_by_room_display = {room.id: [] for room in rooms}
    for booking in bookings_today:
        if booking.room_id in bookings_by_room_display:
             display_params = calculate_display_params(booking, current_date, VIEW_START_HOUR, VIEW_END_HOUR)
             if display_params:
                 display_params['user_name'] = booking.user_name
                 bookings_by_room_display[booking.room_id].append(display_params)
    return render_template('day.html',
                           current_date=current_date,
                           rooms=rooms,
                           bookings_by_room_display=bookings_by_room_display,
                           view_start_hour=VIEW_START_HOUR,
                           view_end_hour=VIEW_END_HOUR,
                           hours_in_view=HOURS_IN_VIEW,
                           pixels_per_hour=PIXELS_PER_HOUR)

@app.route('/rooms')
def rooms_list():
    try:
        rooms = Room.query.order_by(Room.name).all()
    except Exception as e:
        print(f"Error fetching rooms list: {e}")
        flash("Could not retrieve the list of rooms.", "danger")
        rooms = []
    return render_template('rooms.html', rooms=rooms)

@app.route('/persons')
def persons_list():
    try:
        persons_tuples = db.session.query(Booking.user_name).distinct().order_by(Booking.user_name).all()
        persons = [p[0] for p in persons_tuples]
    except Exception as e:
        print(f"Error fetching persons list: {e}")
        flash("Could not retrieve the list of persons.", "danger")
        persons = []
    return render_template('persons.html', persons=persons)

@app.route('/room/<int:room_id>/week')
@app.route('/room/<int:room_id>/week/<int:year>/<int:week_num>')
def week_room_view(room_id, year=None, week_num=None):
    room = Room.query.get_or_404(room_id)
    today = date.today()
    current_year_iso, current_week_iso, _ = today.isocalendar()
    if year is None or week_num is None:
         year, week_num = current_year_iso, current_week_iso
    try:
        start_of_week, end_of_week, days_in_week, prev_year, prev_week, next_year_val, next_week_val, week_label = get_week_data(year, week_num)
    except ValueError:
         flash("Invalid week requested.", "warning")
         year, week_num = current_year_iso, current_week_iso
         start_of_week, end_of_week, days_in_week, prev_year, prev_week, next_year_val, next_week_val, week_label = get_week_data(year, week_num)
    week_start_dt = datetime.combine(start_of_week, time.min)
    week_end_dt = datetime.combine(end_of_week + timedelta(days=1), time.min)
    room_bookings = Booking.query.filter(
        Booking.room_id == room_id,
        Booking.start_time < week_end_dt,
        Booking.end_time > week_start_dt
    ).order_by(Booking.start_time).all()
    bookings_by_day_display = {d: [] for d in days_in_week}
    for booking in room_bookings:
        for day_in_week in days_in_week:
             display_params = calculate_display_params(booking, day_in_week, VIEW_START_HOUR, VIEW_END_HOUR)
             if display_params:
                 display_params['user_name'] = booking.user_name
                 if day_in_week in bookings_by_day_display:
                     bookings_by_day_display[day_in_week].append(display_params)
                 else:
                    print(f"Warning: Day {day_in_week} not found.")
    return render_template('week_room.html',
                           room=room,
                           week_label=week_label,
                           days_in_week=days_in_week,
                           bookings_by_day_display=bookings_by_day_display,
                           current_year=year,
                           current_week=week_num,
                           prev_year=prev_year,
                           prev_week=prev_week,
                           next_year=next_year_val,
                           next_week=next_week_val,
                           view_start_hour=VIEW_START_HOUR,
                           view_end_hour=VIEW_END_HOUR,
                           hours_in_view=HOURS_IN_VIEW,
                           pixels_per_hour=PIXELS_PER_HOUR)


@app.route('/user/<string:user_name>/week')
@app.route('/user/<string:user_name>/week/<int:year>/<int:week_num>')
def week_user_view(user_name, year=None, week_num=None):
    today = date.today()
    current_year_iso, current_week_iso, _ = today.isocalendar()
    if year is None or week_num is None:
        year, week_num = current_year_iso, current_week_iso
    try:
        start_of_week, end_of_week, days_in_week, prev_year, prev_week, next_year_val, next_week_val, week_label = get_week_data(year, week_num)
    except ValueError:
         flash("Invalid week requested.", "warning")
         year, week_num = current_year_iso, current_week_iso
         start_of_week, end_of_week, days_in_week, prev_year, prev_week, next_year_val, next_week_val, week_label = get_week_data(year, week_num)
    week_start_dt = datetime.combine(start_of_week, time.min)
    week_end_dt = datetime.combine(end_of_week + timedelta(days=1), time.min)
    user_bookings = Booking.query.filter(
        Booking.user_name == user_name,
        Booking.start_time < week_end_dt,
        Booking.end_time > week_start_dt
    ).order_by(Booking.start_time).all()
    bookings_by_day_display = {d: [] for d in days_in_week}
    for booking in user_bookings:
        for day_in_week in days_in_week:
             display_params = calculate_display_params(booking, day_in_week, VIEW_START_HOUR, VIEW_END_HOUR)
             if display_params:
                 try:
                     display_params['room_name'] = booking.room.name
                 except Exception:
                    display_params['room_name'] = 'Unknown'
                 if day_in_week in bookings_by_day_display:
                    bookings_by_day_display[day_in_week].append(display_params)
                 else:
                    print(f"Warning: Day {day_in_week} not found.")
    return render_template('week_user.html',
                           user_name=user_name,
                           week_label=week_label,
                           days_in_week=days_in_week,
                           bookings_by_day_display=bookings_by_day_display,
                           current_year=year,
                           current_week=week_num,
                           prev_year=prev_year,
                           prev_week=prev_week,
                           next_year=next_year_val,
                           next_week=next_week_val,
                           view_start_hour=VIEW_START_HOUR,
                           view_end_hour=VIEW_END_HOUR,
                           hours_in_view=HOURS_IN_VIEW,
                           pixels_per_hour=PIXELS_PER_HOUR)

@app.route('/booking/new', methods=['GET', 'POST'])
@app.route('/booking/edit/<int:booking_id>', methods=['GET', 'POST'])
def booking_form(booking_id=None):
    is_edit = booking_id is not None
    booking = None
    cancel_url_unencoded = None
    default_cancel_url = url_for('month_view')

    if is_edit:
        booking = Booking.query.get_or_404(booking_id)
        ref_url_encoded = request.args.get('ref_url')
        if ref_url_encoded:
            try:
                cancel_url_unencoded = unquote(ref_url_encoded)
                if not cancel_url_unencoded or not cancel_url_unencoded.startswith('/'):
                     cancel_url_unencoded = None
            except Exception:
                 cancel_url_unencoded = None

    if request.method == 'POST':
        cancel_url_unencoded = request.form.get('cancel_url_hidden')
        if not cancel_url_unencoded or not cancel_url_unencoded.startswith('/'):
             cancel_url_unencoded = default_cancel_url

        try:
            room_id = int(request.form['room_id'])
            user_name = request.form['user_name'].strip()
            title = request.form['title'].strip()
            details = request.form.get('details', '').strip()
            date_str = request.form['date']
            start_time_str = request.form['start_time']
            end_time_str = request.form['end_time']

            if not all([room_id, user_name, title, date_str, start_time_str, end_time_str]):
                 flash("Please fill in all required fields.", "warning")
                 rooms = Room.query.order_by(Room.name).all()
                 return render_template('booking_form.html', booking=booking, rooms=rooms, is_edit=is_edit, form_data=request.form, cancel_url=cancel_url_unencoded), 400

            booking_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            start_t = datetime.strptime(start_time_str, '%H:%M').time()
            end_t = datetime.strptime(end_time_str, '%H:%M').time()
            start_dt = datetime.combine(booking_date, start_t)
            end_dt = datetime.combine(booking_date, end_t)

            if end_dt <= start_dt:
                flash("End time must be after start time.", "warning")
                rooms = Room.query.order_by(Room.name).all()
                return render_template('booking_form.html', booking=booking, rooms=rooms, is_edit=is_edit, form_data=request.form, cancel_url=cancel_url_unencoded), 400

            overlapping = Booking.query.filter(
                Booking.room_id == room_id,
                Booking.id != booking_id,
                Booking.start_time < end_dt,
                Booking.end_time > start_dt
            ).all()
            if overlapping:
                 conflict_details = ", ".join([f"'{b.title}' ({b.start_time.strftime('%H:%M')}-{b.end_time.strftime('%H:%M')})" for b in overlapping])
                 flash(f"Time slot conflicts with: {conflict_details} in Room {Room.query.get(room_id).name}.", "danger")
                 rooms = Room.query.order_by(Room.name).all()
                 return render_template('booking_form.html', booking=booking, rooms=rooms, is_edit=is_edit, form_data=request.form, cancel_url=cancel_url_unencoded), 400

            if is_edit:
                booking.room_id = room_id
                booking.user_name = user_name
                booking.title = title
                booking.details = details
                booking.start_time = start_dt
                booking.end_time = end_dt
                flash(f"Booking '{title}' updated successfully!", "success")
            else:
                new = Booking(room_id=room_id, user_name=user_name, title=title, details=details, start_time=start_dt, end_time=end_dt)
                db.session.add(new)
                flash(f"Booking '{title}' created successfully!", "success")

            db.session.commit()

            return redirect(cancel_url_unencoded)

        except Exception as e:
            db.session.rollback()
            flash(f"An error occurred: {e}", "danger")
            print(f"Error in booking form: {e}")
            rooms = Room.query.order_by(Room.name).all()
            return render_template('booking_form.html', booking=booking, rooms=rooms, is_edit=is_edit, form_data=request.form, cancel_url=cancel_url_unencoded), 500

    rooms = Room.query.order_by(Room.name).all()
    form_data = None
    if not is_edit and request.args:
         prefill_data = {k: request.args.get(k, '') for k in ['room_id', 'date', 'user_name', 'title', 'start_time']}
         st = prefill_data.get('start_time')
         if st and ':' not in st:
             try:
                prefill_data['start_time'] = f"{int(st):02d}:00"
             except ValueError:
                prefill_data['start_time'] = None
         form_data = prefill_data
         ref_url_encoded = request.args.get('ref_url')
         if ref_url_encoded:
              try:
                   cancel_url_unencoded = unquote(ref_url_encoded)
                   if not cancel_url_unencoded or not cancel_url_unencoded.startswith('/'):
                       cancel_url_unencoded = None
              except Exception:
                   cancel_url_unencoded = None
         else:
              cancel_url_unencoded = None

    if not cancel_url_unencoded:
         if is_edit and booking:
             cancel_url_unencoded = url_for('day_view', year=booking.start_time.year, month=booking.start_time.month, day=booking.start_time.day)
         else:
              cancel_url_unencoded = default_cancel_url

    return render_template('booking_form.html',
                           booking=booking,
                           rooms=rooms,
                           is_edit=is_edit,
                           form_data=form_data,
                           cancel_url=cancel_url_unencoded)


@app.route('/booking/delete/<int:booking_id>', methods=['POST'])
def delete_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    redirect_url = url_for('day_view', year=booking.start_time.year, month=booking.start_time.month, day=booking.start_time.day)
    if request.referrer and request.referrer.startswith(request.host_url):
         if '/booking/delete/' not in request.referrer and '/booking/edit/' not in request.referrer:
              redirect_url = request.referrer
    try:
         db.session.delete(booking)
         db.session.commit()
         flash(f"Booking '{booking.title}' deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting booking: {e}", "danger")
        print(f"Error deleting booking: {e}")
    return redirect(redirect_url)


@app.template_filter('strftime')
def _jinja2_filter_datetime(dt, fmt=None):
    if not isinstance(dt, (datetime, date)):
        return dt
    return dt.strftime(fmt if fmt else '%Y-%m-%d %H:%M')

@app.template_filter('timeformat')
def _jinja2_filter_time(t, fmt='%H:%M'):
    if not isinstance(t, time):
        return t
    return t.strftime(fmt)

if __name__ == '__main__':
    with app.app_context():
        initialize_database()
    app.run(debug=True)