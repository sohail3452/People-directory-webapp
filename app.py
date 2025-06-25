import os
import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'super-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///people.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Models
class Admin(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)

class Person(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=False)
    race = db.Column(db.String(50))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    school = db.Column(db.String(100))
    city = db.Column(db.String(100))
    tags = db.Column(db.String(200))

    images = db.relationship('PersonImage', backref='person', cascade='all, delete-orphan')

    @property
    def age(self):
        today = datetime.date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )

class PersonImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(300), nullable=False)
    person_id = db.Column(db.Integer, db.ForeignKey('person.id'), nullable=False)

# Create database and default admin
def create_tables_and_admin():
    with app.app_context():
        db.create_all()
        if not Admin.query.first():
            admin = Admin(username='admin', password='admin')  # default admin
            db.session.add(admin)
            db.session.commit()

@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))

# Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        admin = Admin.query.filter_by(username=username, password=password).first()
        if admin:
            login_user(admin)
            return redirect(url_for('index'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    people = Person.query.all()
    return render_template('index.html', people=people)

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        files = request.files.getlist('images')
        if not files or all(f.filename == '' for f in files):
            flash('Please upload at least one image.')
            return redirect(request.url)

        try:
            dob = datetime.datetime.strptime(request.form['date_of_birth'], '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format, please use YYYY-MM-DD.')
            return redirect(request.url)

        person = Person(
            full_name=request.form['full_name'],
            date_of_birth=dob,
            race=request.form.get('race'),
            phone=request.form.get('phone'),
            email=request.form.get('email'),
            school=request.form.get('school'),
            city=request.form.get('city'),
            tags=request.form.get('tags')
        )
        db.session.add(person)
        db.session.commit()

        for file in files:
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)

                image = PersonImage(filename=filename, person_id=person.id)
                db.session.add(image)

        db.session.commit()
        flash('Person added successfully with images!')
        return redirect(url_for('index'))

    return render_template('add.html')

@app.route('/person/<int:person_id>')
@login_required
def view(person_id):
    person = Person.query.get_or_404(person_id)
    return render_template('view.html', person=person)

@app.route('/edit/<int:person_id>', methods=['GET', 'POST'])
@login_required
def edit(person_id):
    person = Person.query.get_or_404(person_id)

    if request.method == 'POST':
        try:
            person.full_name = request.form['full_name']
            person.date_of_birth = datetime.datetime.strptime(request.form['date_of_birth'], '%Y-%m-%d').date()
            person.race = request.form.get('race')
            person.phone = request.form.get('phone')
            person.email = request.form.get('email')
            person.school = request.form.get('school')
            person.city = request.form.get('city')
            person.tags = request.form.get('tags')

            files = request.files.getlist('images')
            for file in files:
                if file and file.filename != '':
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    image = PersonImage(filename=filename, person_id=person.id)
                    db.session.add(image)

            db.session.commit()
            flash('Changes saved successfully.')
            return redirect(url_for('view', person_id=person.id))
        except Exception as e:
            flash(f'Error: {e}')
            return redirect(request.url)

    return render_template('edit.html', person=person)

@app.route('/delete_image', methods=['POST'])
@login_required
def delete_image():
    image_id = request.form.get('image_id')
    image = PersonImage.query.get_or_404(image_id)

    try:
        # Delete file from disk
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], image.filename)
        if os.path.exists(filepath):
            os.remove(filepath)

        # Delete record from database
        db.session.delete(image)
        db.session.commit()
        flash('Image deleted successfully.')
    except Exception as e:
        flash(f'Failed to delete image: {e}')

    return redirect(request.referrer or url_for('index'))

@app.route('/delete/<int:person_id>', methods=['POST'])
@login_required
def delete(person_id):
    person = Person.query.get_or_404(person_id)
    try:
        # Delete all images files related to the person
        for image in person.images:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], image.filename)
            if os.path.exists(filepath):
                os.remove(filepath)

        # Delete person (which cascades images)
        db.session.delete(person)
        db.session.commit()
        flash('Person deleted successfully.')
    except Exception as e:
        flash(f'Error deleting person: {e}')

    return redirect(url_for('index'))

@app.route('/search')
@login_required
def search():
    query = request.args.get('q', '')
    results = []
    if query:
        results = Person.query.filter(
            (Person.full_name.ilike(f'%{query}%')) |
            (Person.race.ilike(f'%{query}%')) |
            (Person.tags.ilike(f'%{query}%')) |
            (Person.email.ilike(f'%{query}%')) |
            (Person.city.ilike(f'%{query}%')) |
            (Person.school.ilike(f'%{query}%'))
        ).all()
    return render_template('search.html', people=results, query=query)

# Run app
if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    create_tables_and_admin()
    app.run(debug=True)
