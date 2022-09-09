from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///feedbacks.db"
db = SQLAlchemy(app)
cors = CORS(app)
app.config["CORS_HEADERS"] = "Content-Type"


class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False)
    feedback_type = db.Column(db.String, unique=False)
    feedback_rating = db.Column(db.String)
    feedback_text = db.Column(db.Text)

    def __repr__(self):
        return f"{self.timestamp}: {self.feedback_type}: {self.feedback_text}"


# db.create_all()
# db.session.add(Feedback(
#     timestamp = datetime.now(),
#     feedback_type = 'Transcription Module',
#     feedback_text = 'The transcription time is slow.'
# ))
# db.session.commit()


@app.route("/", methods=["GET"])
def main():
    return "Feedback API"


@app.route("/clear_the_database_please_use_wisely", methods=["GET"])
@cross_origin()
def reset():
    db.drop_all()
    db.create_all()
    return {
        "Reset": "All data is deleted and reset. Hope that is what you wanted to do :P"
    }


@app.route("/view", methods=["GET"])
@cross_origin()
def view_all():
    all_feedbacks = Feedback.query.all()
    feedback_dicts = []
    for f in all_feedbacks:
        feedback_dicts.append(
            {
                "id": f.id,
                "timestamp": f.timestamp,
                "feedback_type": f.feedback_type,
                "feedback_rating": f.feedback_rating,
                "feedback_text": f.feedback_text,
            }
        )
    return jsonify(feedback_dicts)


@app.route("/feedback", methods=["POST"])
@cross_origin()
def feedback():
    db.session.add(
        Feedback(
            timestamp=datetime.now(),
            feedback_type=request.form["feedback_type"],
            feedback_text=request.form["feedback_text"],
            feedback_rating=request.form["feedback_rating"],
        )
    )
    db.session.commit()
    return {"success": True}
