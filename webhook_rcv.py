import datetime
import logging
import os

import psycopg2
import psycopg2.extensions
from flask import Flask, request, Response


class DB:
    db: psycopg2.extensions.connection

    def __init__(self):
        self.db = None

    def connect(self):
        self.db = psycopg2.connect(
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            database=os.environ["POSTGRES_DB"],
            host=os.environ["POSTGRES_HOST"],
        )
        _c = self.db.cursor()
        _c.execute("SELECT version();")
        record = _c.fetchone()
        print("Connected to ", record)
        _c.close()

    def write_to_db(self, id: int, last_vote: datetime.datetime):
        if not self.db:
            self.connect()
        try:
            cursor = self.db.cursor()
            cursor.execute(
                "INSERT INTO polls.users (id, last_vote) VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET last_vote = %s",
                (id, last_vote, last_vote),
            )
            self.db.commit()
            cursor.close()
        except psycopg2.OperationalError:
            self.connect()
            self.write_to_db(id, last_vote)


db = DB()
app = Flask(__name__)


@app.route("/topgg", methods=["POST"])
def top_gg():
    if request.headers.get("Authorization") != os.environ["TOPGG_WEBHOOK_SECRET"]:
        return Response(status=401)

    if request.json.get("type", "test") != "test":
        db.write_to_db(request.json["user"], datetime.datetime.now())
    return Response(status=200)


@app.route("/ping", methods=["GET"])
def ping():
    return "<h1>pong</h1>"


if __name__ == "__main__":
    from waitress import serve
    from dotenv import load_dotenv
    from paste.translogger import TransLogger

    logging.getLogger("waitress").setLevel(logging.INFO)

    load_dotenv()

    serve(TransLogger(app), host="0.0.0.0", port=80)
