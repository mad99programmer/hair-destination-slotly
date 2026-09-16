import os
import json
import firebase_admin
from firebase_admin import credentials, messaging


def init_firebase():
    if firebase_admin._apps:
        return firebase_admin.get_app()

    raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

    if not raw:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON is not set")

    cred = credentials.Certificate(json.loads(raw))
    return firebase_admin.initialize_app(cred)


def send_admin_notification(token, appointment, user, branch, service):
    if not token:
        return

    init_firebase()

    message = messaging.Message(
        token=token,
        notification=messaging.Notification(
            title="New Appointment Booked",
            body=(
                f"{user.name} • {service.name} • {branch.name} • "
                f"{appointment.appointment_date} "
                f"{appointment.start_time.strftime('%I:%M %p')}"
            )
        ),
        data={
            "type": "new_appointment",
            "appointment_id": str(appointment.id),
        }
    )

    messaging.send(message)