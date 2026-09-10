import os
import requests
from dotenv import load_dotenv
import json
import logging
import base64
from datetime import datetime, timezone
from datetime import date
from fastapi import FastAPI, Request, Depends
from fastapi.responses import PlainTextResponse
from database import engine
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from admin_routes import router as admin_router
from auth_routes import router as auth_router
from models import (
    Base,
    User,
    Appointment,
    Branch,
    Service,
    FlowSession
)

from zoneinfo import ZoneInfo
from db_queries import (
    get_branches,
    get_services,
    get_available_slots
    
)
from sqlalchemy.orm import Session
from database import engine, SessionLocal
from flow_crypto import (
    decrypt_aes_key,
    decrypt_flow_data,
    encrypt_response
)
from messaging import send_reply
from handlers import process_message
import time
load_dotenv()
BUSINESS_ID = int(
    os.getenv("BUSINESS_ID", "1")
)
# ==========================================================
# LOGGING
# ==========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(
    "hair-destination-slotly"
)


# ==========================================================
# FASTAPI
# ==========================================================




print("Server datetime :", datetime.now())
print("UTC datetime    :", datetime.now(timezone.utc))
print("IST datetime    :", datetime.now(ZoneInfo("Asia/Kolkata")))

# ==========================================================
# CREATE DATABASE TABLES
# ==========================================================

Base.metadata.create_all(
    bind=engine
)

logger.info(
    "Database tables checked successfully."
)

#handling double message from zernio 
from collections import OrderedDict
import time

_processed_messages = OrderedDict()
_DEDUPE_TTL_SECONDS = 300  # 5 min

def is_duplicate(message_id: str) -> bool:
    now = time.time()
    expired = [mid for mid, ts in _processed_messages.items() if now - ts > _DEDUPE_TTL_SECONDS]
    for mid in expired:
        _processed_messages.pop(mid, None)
    if message_id in _processed_messages:
        return True
    _processed_messages[message_id] = now
    return False

#temporary admin creation


from models import Admin
from security import hash_password

db = SessionLocal()

try:
    admin = db.query(Admin).filter(
        Admin.username == "admin"
    ).first()

    if not admin:
        admin = Admin(
            username="admin",
            password_hash=hash_password("Admin@123")
        )

        db.add(admin)
        db.commit()

finally:
    db.close()

app = FastAPI(
    title="Hair Destination Slotly"
)

# ==========================================================
# ADMIN FRONTEND PAGES
# ==========================================================

@app.get("/admin/login/")
async def admin_login_page():
    return FileResponse("admin/login.html")


@app.get("/admin/dashboard/")
async def admin_dashboard_page():
    return FileResponse("admin/dashboard.html")


@app.get("/admin/appointments/")
async def admin_appointments_page():
    return FileResponse("admin/appointments.html")
app.include_router(admin_router)
app.include_router(auth_router)
app.mount("/admin", StaticFiles(directory="admin", html=True), name="admin")


# =========================
# DATABASE SESSION
# =========================
def get_db():

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()


# ==========================================================
# HEALTH CHECK
# ==========================================================

@app.get("/")
async def health_check():

    return {
        "status": "Hair Destination Slotly is alive"
    }


# ==========================================================
# WHATSAPP FLOW WEBHOOK
# ==========================================================

@app.post("/webhook/whatsapp-flow")
async def whatsapp_flow(
    request: Request
):

    try:

        # ==================================================
        # RECEIVE REQUEST
        # ==================================================

        body = await request.json()

        logger.info(
            "\n%s\nWHATSAPP FLOW REQUEST\n%s",
            "=" * 60,
            "=" * 60
        )

        logger.info(
            json.dumps(
                body,
                indent=2,
                ensure_ascii=False
            )
        )


        # ==================================================
        # GET ENCRYPTED VALUES
        # ==================================================

        encrypted_flow_data = body[
            "encrypted_flow_data"
        ]

        encrypted_aes_key = body[
            "encrypted_aes_key"
        ]

        initial_vector = body[
            "initial_vector"
        ]


        # ==================================================
        # DECODE INITIAL VECTOR
        # ==================================================

        iv = base64.b64decode(
            initial_vector
        )


        # ==================================================
        # DECRYPT AES KEY
        # ==================================================

        aes_key = decrypt_aes_key(
            encrypted_aes_key
        )

        logger.info(
            "AES key decrypted successfully."
        )


        # ==================================================
        # DECRYPT FLOW DATA
        # ==================================================

        decrypted_data = decrypt_flow_data(
            encrypted_flow_data,
            aes_key,
            iv
        )

        logger.info(
            "\nDECRYPTED DATA:\n%s",
            json.dumps(
                decrypted_data,
                indent=2,
                ensure_ascii=False
            )
        )


        # ==================================================
        # GET ACTION
        # ==================================================

        action = decrypted_data.get(
            "action"
        )

        logger.info(
            "ACTION: %s",
            action
        )


        # ==================================================
        # INIT
        # ==================================================

        if action == "INIT":

            logger.info(
                "Handling INIT..."
            )

            response_data = handle_init()


        # ==================================================
        # PING
        # ==================================================

        elif action == "ping":

            logger.info(
                "Handling PING..."
            )

            response_data = {

                "data": {

                    "status": "active"

                }

            }


        # ==================================================
        # DATA EXCHANGE
        # ==================================================

        elif action == "data_exchange":

            logger.info(
                "Handling DATA_EXCHANGE..."
            )

            data = decrypted_data.get(
                "data",
                {}
            )


            # ==================================================
            # GET FORM VALUES
            # ==================================================

            name = data.get(
                "name"
            )

            branch_id = data.get(
                "branch_id"
            )

            service_id = data.get(
                "service_id"
            )

            appointment_date = data.get(
                "date"
            )

            selected_slot = data.get(
                "selected_slot"
            )


            logger.info(
                "Booking data | "
                "name=%s | "
                "branch_id=%s | "
                "service_id=%s | "
                "date=%s | "
                "selected_slot=%s",
                name,
                branch_id,
                service_id,
                appointment_date,
                selected_slot
            )


            # ==================================================
            # FINAL BOOKING CONFIRMATION
            # ==================================================


            ####

            if selected_slot:

                logger.info(
                    "FINAL BOOKING CONFIRMATION RECEIVED."
                )

                logger.info(
                    "Selected slot = %s",
                    selected_slot
                )

                from database import SessionLocal

                db = SessionLocal()

                try:

                    # ==================================================
                    # RESOLVE USER FROM FLOW TOKEN
                    # ==================================================

                    flow_token = decrypted_data.get(
                        "flow_token",
                        ""
                    )

                    session_id = (
                        flow_token.split(":", 1)[1]
                        if ":" in flow_token
                        else flow_token
                    )

                    logger.info(
                        "Resolving FlowSession | session_id=%s",
                        session_id
                    )

                    flow_session = (
                        db.query(FlowSession)
                        .filter(
                            FlowSession.session_id == session_id
                        )
                        .first()
                    )

                    if not flow_session:

                        logger.error(
                            "FlowSession not found | session_id=%s",
                            session_id
                        )

                        raise ValueError(
                            f"FlowSession not found: {session_id}"
                        )

                    user_number = flow_session.phone_number

                    logger.info(
                        "FlowSession resolved | "
                        "session_id=%s | phone=%s",
                        session_id,
                        user_number
                    )

                    # ==================================================
                    # VALIDATE REQUIRED DATA
                    # ==================================================

                    if (
                        not name
                        or not branch_id
                        or not service_id
                        or not appointment_date
                        or not selected_slot
                    ):

                        logger.warning(
                            "Incomplete booking data received."
                        )

                        response_data = {
                            "screen": "BOOKING_DETAILS",
                            "data": {}
                        }

                    else:

                        # ==================================================
                        # CONVERT IDS / DATE
                        # ==================================================

                        branch_id = int(branch_id)
                        service_id = int(service_id)

                        appointment_date = datetime.strptime(
                            appointment_date,
                            "%Y-%m-%d"
                        ).date()

                        # ==================================================
                        # PARSE SLOT
                        #
                        # Example:
                        # 1000_1100
                        # ==================================================

                        try:

                            start_str, end_str = selected_slot.split("_")

                            start_time = datetime.strptime(
                                start_str,
                                "%H%M"
                            ).time()

                            end_time = datetime.strptime(
                                end_str,
                                "%H%M"
                            ).time()

                        except ValueError:

                            logger.error(
                                "Invalid selected_slot format: %s",
                                selected_slot
                            )

                            response_data = {
                                "screen": "BOOKING_DETAILS",
                                "data": {}
                            }

                            raise ValueError(
                                f"Invalid selected slot: {selected_slot}"
                            )

                        # ==================================================
                        # VALIDATE BRANCH
                        # ==================================================

                        branch = (
                            db.query(Branch)
                            .filter(
                                Branch.id == branch_id,
                                Branch.business_id == BUSINESS_ID,
                                Branch.is_active == True
                            )
                            .first()
                        )

                        if not branch:

                            logger.warning(
                                "Invalid branch_id=%s",
                                branch_id
                            )

                            response_data = {
                                "screen": "BOOKING_DETAILS",
                                "data": {}
                            }

                        else:

                            # ==================================================
                            # VALIDATE SERVICE
                            # ==================================================

                            service = (
                                db.query(Service)
                                .filter(
                                    Service.id == service_id,
                                    Service.business_id == BUSINESS_ID,
                                    Service.is_active == True
                                )
                                .first()
                            )

                            if not service:

                                logger.warning(
                                    "Invalid service_id=%s",
                                    service_id
                                )

                                response_data = {
                                    "screen": "BOOKING_DETAILS",
                                    "data": {}
                                }

                            else:

                                # ==================================================
                                # CHECK SLOT CAPACITY AGAIN
                                #
                                # IMPORTANT:
                                # Slot may have become unavailable after
                                # SESSION was displayed.
                                # ==================================================

                                booked_count = (
                                    db.query(Appointment)
                                    .filter(
                                        Appointment.branch_id == branch_id,
                                        Appointment.appointment_date == appointment_date,
                                        Appointment.start_time == start_time,
                                        Appointment.status == "booked"
                                    )
                                    .count()
                                )

                                logger.info(
                                    "Booking validation | "
                                    "branch=%s | date=%s | "
                                    "start=%s | booked=%s | capacity=%s",
                                    branch_id,
                                    appointment_date,
                                    start_time,
                                    booked_count,
                                    branch.capacity
                                )

                                # ==================================================
                                # SLOT NO LONGER AVAILABLE
                                # ==================================================

                                if booked_count >= branch.capacity:

                                    logger.warning(
                                        "Selected slot is no longer available."
                                    )

                                    response_data = {

                                        "screen": "SESSION",

                                        "data": {

                                            "name": name,

                                            "branch_id": str(
                                                branch_id
                                            ),

                                            "service_id": str(
                                                service_id
                                            ),

                                            "date": (
                                                appointment_date.isoformat()
                                            ),

                                            "available_slots": []

                                        }

                                    }

                                else:

                                    # ==================================================
                                    # FIND / CREATE USER
                                    # ==================================================

                                    user = (
                                        db.query(User)
                                        .filter(
                                            User.phone_number == user_number
                                        )
                                        .first()
                                    )

                                    if user:

                                        logger.info(
                                            "Existing user found | "
                                            "user_id=%s | phone=%s",
                                            user.id,
                                            user_number
                                        )

                                        # Update name if supplied
                                        user.name = name

                                        # Keep business association current
                                        user.business_id = BUSINESS_ID

                                    else:

                                        logger.info(
                                            "Creating new user | phone=%s",
                                            user_number
                                        )

                                        user = User(
                                            business_id=BUSINESS_ID,
                                            phone_number=user_number,
                                            name=name,
                                            is_active=True
                                        )

                                        db.add(user)

                                        # Get generated user.id
                                        db.flush()

                                    # ==================================================
                                    # CREATE APPOINTMENT
                                    # ==================================================

                                    appointment = Appointment(

                                        user_id=user.id,

                                        business_id=BUSINESS_ID,

                                        branch_id=branch_id,

                                        service_id=service_id,

                                        branch_slot_id=None,

                                        appointment_date=appointment_date,

                                        start_time=start_time,

                                        end_time=end_time,

                                        status="booked"

                                    )

                                    db.add(appointment)

                                    db.commit()

                                    db.refresh(appointment)

                                    logger.info(
                                        "APPOINTMENT BOOKED SUCCESSFULLY | "
                                        "appointment_id=%s | "
                                        "user_id=%s | "
                                        "phone=%s | "
                                        "branch=%s | "
                                        "service=%s | "
                                        "date=%s | "
                                        "start=%s | "
                                        "end=%s",
                                        appointment.id,
                                        user.id,
                                        user_number,
                                        branch_id,
                                        service_id,
                                        appointment_date,
                                        start_time,
                                        end_time
                                    )

                                    # ==================================================
                                    # SUCCESS SCREEN
                                    # ==================================================

                                    response_data = {

                                        "screen": "BOOKING_SUCCESS",

                                        "data": {}

                                    }

                except Exception:

                    db.rollback()

                    logger.exception(
                        "Final appointment booking failed."
                    )

                    response_data = {

                        "screen": "BOOKING_DETAILS",

                        "data": {}

                    }

                finally:

                    db.close()
            

            # ==================================================
            # CHECK AVAILABILITY
            # ==================================================

            else:

                # --------------------------------------------------
                # VALIDATE REQUIRED VALUES
                # --------------------------------------------------

                if (
                    not branch_id
                    or not service_id
                    or not appointment_date
                ):

                    logger.warning(
                        "Missing booking data."
                    )

                    response_data = {

                        "screen": "BOOKING_DETAILS",

                        "data": {}

                    }


                else:

                    from database import SessionLocal

                    db = SessionLocal()

                    try:

                        # ------------------------------------------
                        # CONVERT IDS
                        # ------------------------------------------

                        branch_id = int(
                            branch_id
                        )

                        service_id = int(
                            service_id
                        )


                        # ------------------------------------------
                        # CONVERT DATE
                        # ------------------------------------------

                        appointment_date = datetime.strptime(
                            appointment_date,
                            "%Y-%m-%d"
                        ).date()


                        logger.info(
                            "Checking availability | "
                            "branch_id=%s | date=%s",
                            branch_id,
                            appointment_date
                        )


                        # ------------------------------------------
                        # GET AVAILABLE SLOTS
                        # ------------------------------------------

                        available_slots = get_available_slots(

                            db=db,

                            branch_id=branch_id,

                            slot_date=appointment_date

                        )


                        logger.info(
                            "Backend returned %d available slots.",
                            len(available_slots)
                        )


                        # ==================================================
                        # IMPORTANT
                        #
                        # get_available_slots() returns:
                        #
                        # {
                        #     "start_time": time(...),
                        #     "end_time": time(...),
                        #     "remaining": 3
                        # }
                        #
                        # So DO NOT use item["slot"].
                        # ==================================================


                        logger.info(
                            "AVAILABLE SLOTS RAW:\n%s",
                            json.dumps(
                                [
                                    str(item)
                                    for item in available_slots
                                ],
                                indent=2
                            )
                        )


                        # ------------------------------------------
                        # BUILD FLOW OPTIONS
                        # ------------------------------------------

                        slots = []


                        for item in available_slots:

                            # --------------------------------------
                            # GET SLOT DATA
                            # --------------------------------------

                            start_time = item[
                                "start_time"
                            ]

                            end_time = item[
                                "end_time"
                            ]

                            remaining = item[
                                "remaining"
                            ]


                            # --------------------------------------
                            # SAFETY
                            # --------------------------------------

                            if remaining <= 0:

                                continue


                            # --------------------------------------
                            # AVAILABILITY INDICATOR
                            # --------------------------------------

                            if remaining >= 3:

                                indicator = "🟢"

                            elif remaining == 2:

                                indicator = "🟡"

                            else:

                                indicator = "🔴"


                            # --------------------------------------
                            # FORMAT TIME
                            # --------------------------------------

                            start = start_time.strftime(
                                "%I:%M %p"
                            )

                            end = end_time.strftime(
                                "%I:%M %p"
                            )


                            # --------------------------------------
                            # SLOT ID
                            # --------------------------------------

                            slot_id = (

                                f"{start_time.strftime('%H%M')}"
                                f"_"
                                f"{end_time.strftime('%H%M')}"

                            )


                            # --------------------------------------
                            # SEAT TEXT
                            # --------------------------------------

                            if remaining == 1:

                                seat_text = (
                                    "1 seat available"
                                )

                            else:

                                seat_text = (
                                    f"{remaining} seats available"
                                )


                            # --------------------------------------
                            # ADD FLOW OPTION
                            # --------------------------------------

                            slots.append({

                                "id": slot_id,

                                "title": (
                                    f"{start} - {end} • "
                                    f"{remaining} "
                                    f"{'seat' if remaining == 1 else 'seats'}"
                                )

                            })


                        # ==================================================
                        # SESSION RESPONSE
                        # ==================================================

                        response_data = {

                            "screen": "SESSION",

                            "data": {

                                "name": name,

                                "branch_id": str(
                                    branch_id
                                ),

                                "service_id": str(
                                    service_id
                                ),

                                "date": (
                                    appointment_date.isoformat()
                                ),

                                "available_slots": slots

                            }

                        }


                        logger.info(
                            "Returning %d slots to SESSION.",
                            len(slots)
                        )


                        # ------------------------------------------
                        # NO SLOTS
                        # ------------------------------------------

                        if not slots:

                            logger.warning(
                                "No available slots found."
                            )


                    finally:

                        db.close()


        # ==================================================
        # UNKNOWN ACTION
        # ==================================================

        else:

            logger.warning(
                "Unsupported action: %s",
                action
            )

            response_data = {

                "screen": "BOOKING_DETAILS",

                "data": {}

            }


        # ==================================================
        # LOG RESPONSE
        # ==================================================

        logger.info(
            "\nRESPONSE DATA:\n%s",
            json.dumps(
                response_data,
                indent=2,
                ensure_ascii=False
            )
        )


        # ==================================================
        # ENCRYPT RESPONSE
        # ==================================================

        encrypted_response = encrypt_response(

            response_data,

            aes_key,

            iv

        )

        logger.info(
            "Encrypted response generated successfully."
        )


        # ==================================================
        # RETURN RESPONSE
        # ==================================================

        return PlainTextResponse(

            content=encrypted_response,

            status_code=200

        )


    except Exception:

        logger.exception(
            "WhatsApp Flow error"
        )

        return PlainTextResponse(

            content="",

            status_code=500

        )


# ==========================================================
# INIT HANDLER
# ==========================================================

def handle_init():

    """
    Handles Meta Flow INIT.

    Currently loads:

        - Active branches
        - Active services

    User creation will be handled later.
    """

    from database import SessionLocal

    db = SessionLocal()

    try:

        # --------------------------------------------------
        # GET BRANCHES
        # --------------------------------------------------

        branches = get_branches(
            db
        )


        # --------------------------------------------------
        # GET SERVICES
        # --------------------------------------------------

        services = get_services(
            db
        )


        # --------------------------------------------------
        # BUILD RESPONSE
        # --------------------------------------------------

        response_data = {

            "screen": "BOOKING_DETAILS",

            "data": {

                "branches": branches,

                "services": services,

                "min_date": date.today().isoformat()

            }

        }


        logger.info(
            "INIT loaded %d branches and %d services.",
            len(branches),
            len(services)
        )


        return response_data


    finally:

        db.close()

# =========================
# Zernio WEBHOOK
# =========================
@app.post("/webhook/zernio")
async def webhook_zernio(request: Request, db: Session = Depends(get_db)):
    webhook_start = time.perf_counter()
    payload = await request.json()
    
    print("RAW PAYLOAD:")
    print(
        json.dumps(
            payload,
            indent=4,
            ensure_ascii=False
        )
    )
    logger.info(
        "[WEBHOOK] Received | event=%s",
        payload.get("event")
    )

    if payload.get("event") == "message.received":
        message = payload.get("message", {})
        account = payload.get("account", {})
        message_id = message.get("id")
        #if message_id and is_duplicate(message_id):
        #    return {"status": "duplicate, skipped"}

        user_number = message.get("sender", {}).get("phoneNumber")
        incoming_msg = message.get("text", "").strip()
        conversation_id = message.get("conversationId")
        account_id = account.get("id")
        process_start = time.perf_counter()
        reply = process_message(user_number, incoming_msg, db,webhook_data=payload)
        process_time = (
            time.perf_counter() - process_start
        ) * 1000

        logger.info(
            "[PROCESS] Completed | time=%.2f ms",
            process_time
        )
        send_start = time.perf_counter()
        print("CONVERSATION ID:", conversation_id)
        print("ACCOUNT ID:", account_id)
        if reply is not None:
            send_reply(conversation_id, account_id, reply)
        else:
            logger.info("[ZERNIO] No text reply required | Flow already sent")
        send_time = (
            time.perf_counter() - send_start
        ) * 1000
        logger.info(
            "[ZERNIO] Reply completed | time=%.2f ms",
            send_time
        )

        total_time = (
            time.perf_counter() - webhook_start
        ) * 1000

        logger.info(
            "[WEBHOOK] Completed | total=%.2f ms",
            total_time
        )

    return {"status": "ok"}
