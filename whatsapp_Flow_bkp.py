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

        encrypted_key_bytes = base64.b64decode(
            encrypted_aes_key
        )

        logger.info(
            "RSA DEBUG | ciphertext_len=%d",
            len(encrypted_key_bytes)
        )

        try:

            aes_key = decrypt_aes_key(
                encrypted_aes_key
            )

            logger.info(
                "RSA DEBUG | decrypt SUCCESS | aes_len=%d",
                len(aes_key)
            )

        except Exception:

            logger.exception(
                "RSA DEBUG | decrypt FAILED"
            )

            raise


        # ==================================================
        # DECRYPT FLOW DATA
        # ==================================================

        logger.info(
            "FLOW DEBUG | encrypted_flow_data_len=%d | iv_len=%d",
            len(base64.b64decode(encrypted_flow_data)),
            len(iv)
        )

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

            #response_data = handle_init()
            flow_token = decrypted_data.get("flow_token", "")
            response_data = handle_init(flow_token)


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
                                    flow_session.completed = True
                                    flow_session.completed_at = datetime.now(timezone.utc)
                                    db.commit()
                                    # ==================================================
                                    # SUCCESS SCREEN
                                    # ==================================================

                                    response_data = {
                                        "version": "3.0",
                                        "screen": "BOOKING_SUCCESS",
                                        "data": {
                                            "appointment_id": str(appointment.id),
                                            "date": appointment.appointment_date.strftime("%d %B %Y"),
                                            "time": (
                                                f"{appointment.start_time.strftime('%I:%M %p').lstrip('0')} - "
                                                f"{appointment.end_time.strftime('%I:%M %p').lstrip('0')}"
                                            ),
                                            "branch": branch.name,
                                            "service": service.name
                                        }
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

                        now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
                        today_ist = now_ist.date()
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

                            # Hide past slots only when selected date is today
                            if appointment_date == today_ist:
                                if start_time <= now_ist.time():
                                    continue

                            # --------------------------------------
                            # SAFETY
                            # --------------------------------------

                            if remaining <= 0:

                                continue


                           
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


                            
                            slots.append({

                                "id": slot_id,

                                "title": (
                                    f"{start} - {end}   "
                                    f"{'🪑 ' * remaining}"
                                ).strip()

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
