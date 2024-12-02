# At the top of main.py, update imports
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
import requests
import json
import traceback
from sqlalchemy import inspect
from typing import Optional, Dict, Any, List, TypedDict, NotRequired, cast
import httpx
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
from DatabaseIntegration import MaintenanceRequest, engine
from sqlalchemy import create_engine, text
from app.database.DatabaseIntegration import Base, engine
from app.database.DatabaseIntegration import (
    CustomerSession, 
    SessionLocal,
    get_db,
    DatabaseOperations,
    RequestStatus,
    init_db,
    MaintenanceRequest,
    SessionData
) 

# Instead of extending SessionData, create new type
class MaintenanceState(TypedDict, total=False):
    state: str
    name: NotRequired[str]
    equipment: NotRequired[str]
    problem: NotRequired[str]
    schedule: NotRequired[str]
    photos: NotRequired[List[str]]

MaintenanceRequest.metadata.create_all(bind=engine)

# Configuration
ACCESS_TOKEN = "EAASXI3D5OasBO8seUnG9pRg0FI3ZC1jpbUKl3ZASZBVZClkR1FsMJqMvdeYsC3UDNgEpcR6pIZAtchT7O1NnQSzZBrO31zId2cnKZAdGOUKfas5XtSYaMIt4YapzoYZBkAIYS7MZBxXvpb5jenZCBiRVCY2bR5m1lGEHTHWSAHOl3V0c4nBE1IRwOnCrkUerUWucsZACg0xeulf7ZBV3HQfOqENnQoS2k58ZD"
PHONE_NUMBER_ID = "430698916802809"
TEST_NUMBER = "+1 555 160 3036"
VERIFY_TOKEN = "kitchen2024maintenance"

print(f"Using token starting with: {ACCESS_TOKEN[:10]}")

# Initialize FastAPI app
app = FastAPI()

# Data storage
maintenance_requests: Dict[str, Any] = {}
technicians: Dict[int, Dict[str, Any]] = {
    1: {"name": "Ahmad", "skills": ["oven", "stove"], "location": "Manama", "available": True},
    2: {"name": "Mohammed", "skills": ["refrigerator", "freezer"], "location": "Riffa", "available": True}
}
customer_sessions: Dict[str, Any] = {}
user_languages: Dict[str, str] = {}


# Add handler functions that were missing
async def handle_start_state(db: Session, from_number: str, message: str, session: Dict[str, Any], lang: str) -> str:
    """
    Modified to skip the welcome message and go straight to name collection
    """
    session_data = dict(session)
    session_data["state"] = "awaiting_name"
    DatabaseOperations.update_customer_session(db, from_number, session_data, lang)
    return MESSAGES["maintenance"][lang]["welcome_name"]  # Using new combined message

async def handle_name_state(db: Session, from_number: str, message: str, session: Dict[str, Any], lang: str) -> str:
    session_data = dict(session)
    session_data["name"] = message
    session_data["state"] = "awaiting_equipment"
    DatabaseOperations.update_customer_session(db, from_number, session_data, lang)
    return MESSAGES["maintenance"][lang]["equipment"]

async def handle_equipment_state(db: Session, from_number: str, message: str, session: Dict[str, Any], lang: str) -> str:
    equipment_types = {
        "1": "Cooking Equipment",
        "2": "Refrigeration Equipment",
        "3": "Food Prep Equipment",
        "4": "Other Equipment"
    }
    if message not in equipment_types:
        return MESSAGES["maintenance"][lang]["equipment"]

    session_data = dict(session)
    session_data["equipment"] = equipment_types[message]
    session_data["state"] = "awaiting_problem"
    DatabaseOperations.update_customer_session(db, from_number, session_data, lang)
    return MESSAGES["maintenance"][lang]["problem"]

async def handle_problem_state(db: Session, from_number: str, message: str, session: Dict[str, Any], lang: str) -> str:
    session_data = dict(session)
    session_data["problem"] = message
    session_data["state"] = "awaiting_schedule"
    DatabaseOperations.update_customer_session(db, from_number, session_data, lang)
    return MESSAGES["maintenance"][lang]["schedule"]

async def handle_schedule_state(db: Session, from_number: str, message: str, session: Dict[str, Any], lang: str) -> str:
    schedule_options = {
        "1": "Morning (9 AM - 12 PM)",
        "2": "Afternoon (12 PM - 3 PM)",
        "3": "Evening (3 PM - 6 PM)"
    }
    if message not in schedule_options:
        return MESSAGES["maintenance"][lang]["schedule"]

    session_data = dict(session)
    session_data["schedule"] = schedule_options[message]
    session_data["state"] = "awaiting_confirmation"
    DatabaseOperations.update_customer_session(db, from_number, session_data, lang)
    return MESSAGES["maintenance"][lang]["confirm"].format(
        name=session_data["name"],
        equipment=session_data["equipment"],
        problem=session_data["problem"],
        schedule=session_data["schedule"]
    )

# Add logging to maintenance request creation
async def handle_confirmation_state(db: Session, from_number: str, message: str, session: Dict[str, Any], lang: str) -> str:
    if message == "1":
        try:
            # Create maintenance request
            request_data = {
                "customer_name": session["name"],
                "phone_number": from_number,
                "equipment_type": session["equipment"],
                "problem_description": session["problem"],
                "preferred_time": session["schedule"],
                "status": RequestStatus.PENDING.value,
                "photos": session.get("photos", [])
            }
            print(f"Creating maintenance request with data: {json.dumps(request_data, indent=2)}")

            request = DatabaseOperations.create_maintenance_request(db, request_data)
            print(f"Successfully created request with ID: {request.id}")

            DatabaseOperations.delete_customer_session(db, from_number)
            return MESSAGES["maintenance"][lang]["success"].format(request_id=request.id)
        except Exception as e:
            print(f"Error creating maintenance request: {str(e)}")
            traceback.print_exc()
            return MESSAGES["maintenance"][lang]["error"]
    elif message == "2":
        DatabaseOperations.delete_customer_session(db, from_number)
        return MESSAGES["menu"][lang]
    else:
        return MESSAGES["maintenance"][lang]["confirm"].format(
            name=session["name"],
            equipment=session["equipment"],
            problem=session["problem"],
            schedule=session["schedule"]
        )

async def handle_maintenance_flow(db: Session, from_number: str, message: str, lang: str) -> str:
    try:
        db_session: Optional[CustomerSession] = DatabaseOperations.get_customer_session(db, from_number)

        if db_session is None or not isinstance(db_session.session_data, dict):
            session_data: SessionData = {"state": "awaiting_name"}
            DatabaseOperations.update_customer_session(db, from_number, session_data, lang)
            return MESSAGES["maintenance"][lang]["welcome_name"]

        session_data = cast(SessionData, dict(db_session.session_data))
        state = session_data.get("state", "start")
        print(f"Maintenance flow - Current state: {state}, Message: {message}, Language: {lang}")

        # State machine implementation
        if state == "awaiting_name":
            session_data["name"] = message
            session_data["state"] = "awaiting_phone"
            DatabaseOperations.update_customer_session(db, from_number, session_data, lang)
            return MESSAGES["maintenance"][lang]["phone"]

        # Add location state handling
        elif state == "awaiting_photo":
            if message.lower() != "skip":
                session_data["photos"] = session_data.get("photos", []) + [message]

            session_data["state"] = "awaiting_location"
            DatabaseOperations.update_customer_session(db, from_number, session_data, lang)
            return MESSAGES["maintenance"][lang]["location"]

        elif state == "awaiting_location":
            session_data["state"] = "awaiting_schedule"
            DatabaseOperations.update_customer_session(db, from_number, session_data, lang)
            return MESSAGES["maintenance"][lang]["schedule"]
        
        elif state == "awaiting_phone":
            # Validate phone number format
            if not is_valid_phone(message):
                return MESSAGES["maintenance"][lang]["invalid_phone"]

            session_data["contact_phone"] = message
            session_data["state"] = "awaiting_equipment"
            DatabaseOperations.update_customer_session(db, from_number, session_data, lang)
            return MESSAGES["maintenance"][lang]["equipment"]

        elif state == "awaiting_equipment":
            equipment_types = {
                "1": "Cooking Equipment",
                "2": "Refrigeration Equipment",
                "3": "Food Prep Equipment",
                "4": "Other Equipment"
            }
            if message not in equipment_types:
                return MESSAGES["maintenance"][lang]["equipment"]

            session_data["equipment"] = equipment_types[message]
            session_data["state"] = "awaiting_problem"
            DatabaseOperations.update_customer_session(db, from_number, session_data, lang)
            return MESSAGES["maintenance"][lang]["problem"]

        elif state == "awaiting_problem":
            session_data["problem"] = message
            session_data["state"] = "awaiting_photo"
            DatabaseOperations.update_customer_session(db, from_number, session_data, lang)
            return MESSAGES["maintenance"][lang]["photo"]

        elif state == "awaiting_photo":
            if message.lower() != "skip":
                session_data["photos"] = session_data.get("photos", []) + [message]

            session_data["state"] = "awaiting_schedule"
            DatabaseOperations.update_customer_session(db, from_number, session_data, lang)
            return MESSAGES["maintenance"][lang]["schedule"]

        elif state == "awaiting_schedule":
            schedule_options = {
                "1": "Morning (9 AM - 12 PM)",
                "2": "Afternoon (12 PM - 3 PM)",
                "3": "Evening (3 PM - 6 PM)"
            }
            if message not in schedule_options:
                return MESSAGES["maintenance"][lang]["schedule"]

            session_data["schedule"] = schedule_options[message]
            session_data["state"] = "awaiting_confirmation"
            DatabaseOperations.update_customer_session(db, from_number, session_data, lang)
            return MESSAGES["maintenance"][lang]["confirm"].format(
                name=session_data["name"],
                phone=session_data["contact_phone"],
                equipment=session_data["equipment"],
                problem=session_data["problem"],
                schedule=session_data["schedule"],
                photos="✓" if session_data.get("photos") else "✗"
            )

        elif state == "awaiting_confirmation":
            if message == "1":
                request_data = {
                    "customer_name": session_data["name"],
                    "phone_number": session_data["contact_phone"],
                    "equipment_type": session_data["equipment"],
                    "problem_description": session_data["problem"],
                    "preferred_time": session_data["schedule"],
                    "status": RequestStatus.PENDING.value,
                    "photos": session_data.get("photos", []),
                    "latitude": session_data.get("latitude"),
                    "longitude": session_data.get("longitude"),
                    "location_name": session_data.get("location_name")
                }
                try:
                    request = DatabaseOperations.create_maintenance_request(db, request_data)
                    print(f"Created maintenance request: {request.id}")
                    DatabaseOperations.delete_customer_session(db, from_number)
                    return MESSAGES["maintenance"][lang]                ["success"].format(request_id=request.id)
                except Exception as e:
                    print(f"Error creating maintenance request: {str(e)}")
                    traceback.print_exc()
                    return MESSAGES["maintenance"][lang]["error"]
            elif message == "2":
                DatabaseOperations.delete_customer_session(db, from_number)
                return MESSAGES["menu"][lang]
            else:
                return MESSAGES["maintenance"][lang]["confirm"].format(
                    name=session_data["name"],
                    phone=session_data["contact_phone"],
                    equipment=session_data["equipment"],
                    problem=session_data["problem"],
                    schedule=session_data["schedule"],
                    photos="✓" if session_data.get("photos") else "✗",
                    location="✓" if session_data.get("latitude") else "✗"
                )

    except Exception as e:
        print(f"Error in maintenance flow: {str(e)}")
        traceback.print_exc()
        return MESSAGES["maintenance"][lang]["error"]

def is_valid_phone(phone: str) -> bool:
    """Validate phone number format"""
    # Add your phone validation logic here
    # This is a simple example - adjust according to your needs
    phone = phone.strip().replace(" ", "").replace("-", "").replace("+", "")
    return len(phone) >= 8 and phone.isdigit()

async def handle_menu_option(db: Session, from_number: str, message: str, lang: str) -> str:
    """Handle main menu options"""
    print(f"Handling menu option: {message} for language: {lang}")

    if message == "1":
        return get_catalog_list(lang)
    elif message == "2":
        # Start maintenance flow with clean session
        session_data: SessionData = {"state": "awaiting_name"}
        DatabaseOperations.update_customer_session(db, from_number, session_data, lang)
        return MESSAGES["maintenance"][lang]["welcome_name"]
    elif message == "3":
        return MESSAGES["support"][lang]
    elif message == "4":
        return MESSAGES["feedback"][lang]
    elif message == "5":
        DatabaseOperations.delete_customer_session(db, from_number)
        return MESSAGES["welcome"]["en"] + "\n\n" + MESSAGES["welcome"]["ar"]
    else:
        return MESSAGES["menu"][lang]

def handle_language_selection(message: str) -> Optional[str]:
    """Handle language selection from user input"""
    message = message.strip().lower()
    if message in ["1", "english", "en"]:
        return "en"
    elif message in ["2", "arabic", "ar", "عربي", "العربية"]:
        return "ar"
    return None

async def handle_text_message(db: Session, from_number: str, message_body: str) -> None:
    
    try:
        print(f"\n=== HANDLING MESSAGE START ===")
        print(f"From: {from_number}")
        print(f"Message: {message_body}")
        
        # Get session with proper type checking
        db_session = DatabaseOperations.get_customer_session(db, from_number)
        print(f"Current session: {db_session}")
        if db_session:
            print(f"Session language: {db_session.language}")
            print(f"Session data: {db_session.session_data}")

        # Handle new users
        if db_session is None:
            print("New user detected - creating initial session")
            response = MESSAGES["welcome"]["en"] + "\n\n" + MESSAGES["welcome"]["ar"]
            initial_session: SessionData = {"state": "selecting"}
            DatabaseOperations.update_customer_session(
                db=db,
                phone_number=from_number,
                session_data=initial_session,
                language="selecting"
            )
            print("Sending welcome message")
            await send_whatsapp_message(from_number, response)
            return

        current_language = str(db_session.language) if db_session.language is not None else "en"
        print(f"Current language: {current_language}")

        # Handle language selection
        if current_language == "selecting":
            print("Handling language selection")
            lang = handle_language_selection(message_body)
            if lang:
                print(f"Language selected: {lang}")
                empty_session: SessionData = {"state": ""}
                DatabaseOperations.update_customer_session(db, from_number, empty_session, lang)
                response = MESSAGES["menu"][lang]
            else:
                print("Invalid language selection")
                response = MESSAGES["welcome"]["en"] + "\n\n" + MESSAGES["welcome"]["ar"]
            await send_whatsapp_message(from_number, response)
            return

        # Get session data
        session_data = cast(SessionData, db_session.session_data if db_session.session_data is not None else {})
        state = session_data.get("state", "")
        print(f"Current state: {state}")

        # Handle menu or maintenance flow
        if not state:
            print("Handling menu option")
            response = await handle_menu_option(db, from_number, message_body, current_language)
        else:
            print("Handling maintenance flow")
            if message_body.lower() == "menu":
                empty_session: SessionData = {"state": ""}
                DatabaseOperations.update_customer_session(db, from_number, empty_session, current_language)
                response = MESSAGES["menu"][current_language]
            else:
                response = await handle_maintenance_flow(db, from_number, message_body, current_language)

        print(f"Sending response: {response[:100]}...")
        await send_whatsapp_message(from_number, response)
        print("=== Message handling completed ===")


        print("=== HANDLING MESSAGE END ===\n")
    except Exception as e:
        print(f"ERROR in handle_text_message: {str(e)}")
        traceback.print_exc()
        db_session = DatabaseOperations.get_customer_session(db, from_number)
        lang = "en"
        if db_session and hasattr(db_session, 'language'):
            lang = str(db_session.language) if db_session.language is not None else "en"
        error_message = "An error occurred. Please try again." if lang == "en" else "حدث خطأ. يرجى المحاولة مرة أخرى."
        await send_whatsapp_message(from_number, error_message)

# Equipment categories
equipment_categories = {
    "cooking_equipment": {
        "en": "Cooking Equipment",
        "ar": "معدات الطهي"
    },
    "refrigeration_equipment": {
        "en": "Refrigeration Equipment",
        "ar": "معدات التبريد"
    },
    "food_prep_equipment": {
        "en": "Food Preparation Equipment",
        "ar": "معدات تحضير الطعام"
    },
    "dishwashing_equipment": {
        "en": "Dishwashing Equipment",
        "ar": "معدات غسيل الصحون"
    },
    "storage_equipment": {
        "en": "Storage & Transport Equipment",
        "ar": "معدات التخزين والنقل"
    },
    "serving_equipment": {
        "en": "Serving Equipment",
        "ar": "معدات التقديم"
    },
    "beverage_equipment": {
        "en": "Beverage Equipment",
        "ar": "معدات المشروبات"
    },
    "bakery_equipment": {
        "en": "Bakery Equipment",
        "ar": "معدات المخبز"
    },
    "ventilation_equipment": {
        "en": "Ventilation Equipment",
        "ar": "معدات التهوية"
    },
    "cleaning_equipment": {
        "en": "Cleaning Equipment",
        "ar": "معدات التنظيف"
    },
    "weighing_equipment": {
        "en": "Weighing & Measuring Equipment",
        "ar": "معدات الوزن والقياس"
    },
    "butchery_equipment": {
        "en": "Butchery Equipment",
        "ar": "معدات اللحوم"
    },
    "pizza_equipment": {
        "en": "Pizza Equipment",
        "ar": "معدات البيتزا"
    },
    "ice_equipment": {
        "en": "Ice Making Equipment",
        "ar": "معدات صنع الثلج"
    },
    "warming_equipment": {
        "en": "Food Warming & Holding Equipment",
        "ar": "معدات تسخين وحفظ الطعام"
    },
    "waste_equipment": {
        "en": "Waste Management Equipment",
        "ar": "معدات إدارة النفايات"
    },
    "display_equipment": {
        "en": "Food Display Equipment",
        "ar": "معدات عرض الطعام"
    },
    "safety_equipment": {
        "en": "Safety & Sanitation Equipment",
        "ar": "معدات السلامة والتعقيم"
    }
}

# Message templates
MESSAGES = {
    "welcome": {
        "en": """*Welcome to Marino Kitchen Equipment Services*

Please select your preferred language:

1. English
2. Arabic""",

        "ar": """*أهلاً بكم في خدمات معدات مطابخ مارينو*

الرجاء اختيار لغتك المفضلة:

1. الإنجليزية
2. العربية"""
    },

    "menu": {
        "en": """*How can we help you today?*

Please choose from our services:

1. Equipment Catalog
2. Maintenance Service
3. Technical Support
4. Share Feedback
5. Exit

Need assistance? Our team is here to help.""",

        "ar": """*كيف يمكننا مساعدتك اليوم؟*

الرجاء اختيار من خدماتنا:

1. كتالوج المعدات
2. خدمة الصيانة
3. الدعم الفني
4. شاركنا رأيك
5. خروج

هل تحتاج للمساعدة؟ فريقنا هنا لخدمتك."""
    },

    "maintenance": {
        "en": {
            "welcome_name": """*Kitchen Equipment Maintenance Service*

Let's get started with your service request.
Please enter your name:""",

            "phone": """*Contact Information*

Please enter your phone number:
(e.g., +973XXXXXXXX)""",

            "invalid_phone": """Invalid phone number format.
Please enter a valid phone number starting with country code.
Example: +973XXXXXXXX""",

            "equipment": """*Equipment Type Selection*

Please select your equipment type:

1. Cooking Equipment
2. Refrigeration Equipment
3. Food Prep Equipment
4. Other Equipment""",

            "problem": """*Problem Description*

Please describe the issue with your equipment:
(Be as specific as possible)""",

            "photo": """*Equipment Photo*

Please send a photo of the equipment
or type 'skip' to continue without a photo.

Note: Photos help our technicians prepare better.""",

            "location": """*Location Information*

Please share your location:

1. Press the attachment (+) icon
2. Select 'Location'
3. Send your current location

Or type 'skip' to provide location later.""",

            "photo_received": """Photo received.
Now, please share your location.""",

            "location_received": """Location received.
Let's proceed with scheduling.""",

            "location_skip": """Location sharing skipped.
You can share your location when our technician contacts you.""",

            "schedule": """*Service Scheduling*

Please select your preferred time slot:

1. Morning (9 AM - 12 PM)
2. Afternoon (12 PM - 3 PM)
3. Evening (3 PM - 6 PM)""",

            "confirm": """*Service Request Summary*

Name: {name}
Phone: {phone}
Equipment: {equipment}
Problem: {problem}
Location: {location_status}
Schedule: {schedule}
Photos: {photos}
Initial Fee: 11 BD

Please confirm:
1. Confirm Request
2. Cancel Request""",

            "success": """*Request Confirmed*

Thank you for choosing our service.
Your request has been registered successfully.

Request ID: {request_id}

Our team will contact you shortly to confirm the appointment.

For assistance, contact us at +973XXXXXXXX""",

            "error": """*Error*

Sorry, something went wrong.
Please try again or contact support.

Support: +973XXXXXXXX"""
        },

        "ar": {
            "welcome_name": """*خدمة صيانة معدات المطبخ*

دعنا نبدأ بطلب الخدمة.
الرجاء إدخال اسمك:""",

            "phone": """*معلومات الاتصال*

الرجاء إدخال رقم هاتفك:
(مثال: +973XXXXXXXX)""",

            "invalid_phone": """صيغة رقم الهاتف غير صحيحة.
الرجاء إدخال رقم هاتف صحيح يبدأ برمز الدولة.
مثال: +973XXXXXXXX""",

            "equipment": """*اختيار نوع المعدات*

الرجاء اختيار نوع المعدات:

1. معدات الطهي
2. معدات التبريد
3. معدات تحضير الطعام
4. معدات أخرى""",

            "problem": """*وصف المشكلة*

الرجاء وصف المشكلة في معداتك:
(كن محدداً قدر الإمكان)""",

            "photo": """*صورة المعدات*

الرجاء إرسال صورة للمعدات
أو اكتب 'تخطي' للمتابعة بدون صورة.

ملاحظة: الصور تساعد الفنيين في التحضير بشكل أفضل.""",

            "location": """*معلومات الموقع*

الرجاء مشاركة موقعك باستخدام خاصية الموقع في واتساب:

1. اضغط على أيقونة المرفقات (+)
2. اختر 'الموقع'
3. أرسل موقعك الحالي

أو اكتب 'تخطي' لمشاركة الموقع لاحقاً.""",

            "photo_received": """تم استلام الصورة.
الرجاء مشاركة موقعك.""",

            "location_received": """تم استلام الموقع.
لننتقل إلى جدولة الموعد.""",

            "location_skip": """تم تخطي مشاركة الموقع.
يمكنك مشاركة موقعك عندما يتصل بك الفني.""",

            "schedule": """*جدولة الخدمة*

الرجاء اختيار الوقت المفضل:

1. صباحاً (9 صباحاً - 12 ظهراً)
2. ظهراً (12 ظهراً - 3 عصراً)
3. مساءً (3 عصراً - 6 مساءً)""",

            "confirm": """*ملخص طلب الخدمة*

الاسم: {name}
الهاتف: {phone}
المعدات: {equipment}
المشكلة: {problem}
الموقع: {location_status}
الموعد: {schedule}
الصور: {photos}
الرسوم الأولية: 11 دينار

للتأكيد:
1. تأكيد الطلب
2. إلغاء الطلب""",

            "success": """*تم تأكيد الطلب*

شكراً لاختيارك خدماتنا.
تم تسجيل طلبك بنجاح.

رقم الطلب: {request_id}

سيتصل بك فريقنا قريباً لتأكيد الموعد.

للمساعدة، اتصل بنا على +973XXXXXXXX""",

            "error": """*خطأ*

عذراً، حدث خطأ ما.
الرجاء المحاولة مرة أخرى أو الاتصال بالدعم.

الدعم الفني: +973XXXXXXXX"""
        }
    },

    "catalog": {
        "en": """*Our Equipment Categories*

Visit our website for detailed information:
https://marinobh.com/

Available Categories:
""",
        "ar": """*فئات المعدات لدينا*

زوروا موقعنا للمزيد من المعلومات:
https://marinobh.com/

الفئات المتوفرة:
"""
    },

    "support": {
        "en": """*Customer Support Options*

1. Call: +973 XXXXXXXX
2. Email: support@kitchen-maintenance.com
3. WhatsApp: Reply with your question
4. Live Chat: Visit our website

Operating Hours: 8 AM - 8 PM""",

        "ar": """*خيارات الدعم الفني*

1. اتصل: +973 XXXXXXXX
2. البريد الإلكتروني: support@kitchen-maintenance.com
3. واتساب: أرسل استفسارك
4. الدردشة المباشرة: زر موقعنا

ساعات العمل: 8 صباحاً - 8 مساءً"""
    },

    "feedback": {
        "en": """*Service Feedback*

Please rate our service (1-5 stars) and add your comments.

Format: RATE [stars] [comments]
Example: RATE 5 Great service, very professional""",

        "ar": """*تقييم الخدمة*

الرجاء تقييم خدمتنا (1-5 نجوم) وإضافة تعليقاتك.

الصيغة: RATE [النجوم] [التعليقات]
مثال: RATE 5 خدمة ممتازة ومهنية عالية"""
    }
}

# Data storage
maintenance_requests = {}
technicians = {
    1: {"name": "Ahmad", "skills": ["oven", "stove"], "location": "Manama", "available": True},
    2: {"name": "Mohammed", "skills": ["refrigerator", "freezer"], "location": "Riffa", "available": True}
}
customer_sessions = {}
user_languages = {}

def get_catalog_list(lang: str) -> str:
    """Generate a formatted list of equipment categories in specified language"""
    message = MESSAGES["catalog"][lang]

    for category_id, category in equipment_categories.items():
        message += f"📦 {category[lang]}\n"

    return message

async def send_whatsapp_message(to_number: str, message: str) -> Dict[str, Any]:
    """Send a WhatsApp message using the WhatsApp Business API with better error handling"""
    url = f"https://graph.facebook.com/v17.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_number,
        "type": "text",
        "text": {"preview_url": False, "body": message}
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        print(f"Error sending message to {to_number}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to send WhatsApp message: {str(e)}")

# Add these new debug endpoints
@app.get("/debug/maintenance-state/{phone_number}")
async def debug_maintenance_state(phone_number: str, db: Session = Depends(get_db)):
    
    """Debug endpoint to check maintenance flow state"""
    try:
        # Initialize session to None
        session = None
        try:
            session = DatabaseOperations.get_customer_session(db, phone_number)
        except Exception as e:
            return {"status": "error", "message": f"Error fetching session: {str(e)}"}

        if session and hasattr(session, 'language') and hasattr(session, 'session_data'):
            if isinstance(session.session_data, dict):
                return {
                    "status": "found",
                    "language": session.language,
                    "session_data": session.session_data,
                    "current_state": session.session_data.get("state", "unknown")
                }
        return {"status": "not_found"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/debug/force-state/{phone_number}")
async def force_state(
    phone_number: str, 
    state: str, 
    lang: str = "en", 
    db: Session = Depends(get_db)):
    """Debug endpoint to force a specific state"""
    try:
        session = {"state": state}
        DatabaseOperations.update_customer_session(db, phone_number, session, lang)
        return {"status": "success", "new_state": state}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/webhook")
async def verify_webhook(request: Request):
    """Handle webhook verification from WhatsApp"""
    try:
        mode = request.query_params.get("hub.mode")
        token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge")

        print(f"Verification attempt - Mode: {mode}, Token: {token}, Challenge: {challenge}")

        if mode == "subscribe" and token == VERIFY_TOKEN:
            if challenge:
                return int(challenge)
            return "OK"

        return JSONResponse(
            content={"status": "verify_failed", "received_token": token},
            status_code=403
        )

    except Exception as e:
        print(f"Error in verification: {str(e)}")
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )

@app.post("/webhook") 
async def webhook(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
        print("\n=== WEBHOOK EVENT START ===")
        print("Raw webhook body:", json.dumps(body, indent=2))

        if 'entry' not in body or not body['entry']:
            return JSONResponse(content={"status": "no_entries"})

        for entry in body['entry']:
            changes = entry.get('changes', [])
            for change in changes:
                value = change.get('value', {})

                if 'statuses' in value:
                    print("Status update received - skipping")
                    continue

                if 'messages' in value:
                    messages = value['messages']
                    for message in messages:
                        from_number = message['from']
                        message_type = message.get('type')

                        print(f"Processing {message_type} message from {from_number}")

                        try:
                            if message_type == "text":
                                message_body = message['text']['body']
                                await handle_text_message(db, from_number, message_body)

                            elif message_type == "image":
                                image_id = message['image']['id']
                                # Store the image ID in the session
                                session = DatabaseOperations.get_customer_session(db, from_number)
                                if session and session.session_data.get('state') == 'awaiting_photo':
                                    session_data = dict(session.session_data)
                                    session_data['photos'] = session_data.get('photos', []) + [image_id]
                                    session_data['state'] = "awaiting_location"
                                    DatabaseOperations.update_customer_session(db, from_number, session_data, session.language)

                                    location_message = MESSAGES["maintenance"][session.language]["location"]
                                    await send_whatsapp_message(from_number, location_message)

                            elif message_type == "location":
                                session = DatabaseOperations.get_customer_session(db, from_number)
                                if session and session.session_data.get('state') == 'awaiting_location':
                                    location_data = message.get('location', {})
                                    session_data = dict(session.session_data)

                                    # Store location information
                                    session_data['latitude'] = str(location_data.get('latitude'))
                                    session_data['longitude'] = str(location_data.get('longitude'))
                                    session_data['location_name'] = location_data.get('name', '')
                                    session_data['state'] = "awaiting_schedule"

                                    DatabaseOperations.update_customer_session(
                                        db, 
                                        from_number, 
                                        session_data, 
                                        session.language
                                    )

                                    # Send the schedule message after receiving location
                                    combined_message = (
                                        """📍 *Location received!*

📅 *Service Scheduling*

Please select your preferred time slot:

1️⃣ Morning (9 AM - 12 PM)
2️⃣ Afternoon (12 PM - 3 PM)
3️⃣ Evening (3 PM - 6 PM)""" if session.language == "en" else
                                        """📍 *تم استلام الموقع!*

📅 *جدولة الخدمة*

الرجاء اختيار الوقت المفضل:

1️⃣ صباحاً (9 صباحاً - 12 ظهراً)
2️⃣ ظهراً (12 ظهراً - 3 عصراً)
3️⃣ مساءً (3 عصراً - 6 مساءً)"""
                                    )
                                    await send_whatsapp_message(from_number, combined_message)

                            else:
                                print(f"Unhandled message type: {message_type}")

                        except Exception as msg_error:
                            print(f"Error processing message: {str(msg_error)}")
                            traceback.print_exc()
                            # Send error message to user
                            error_message = ("An error occurred. Please try again." 
                                           if session.language == "en" 
                                           else "حدث خطأ. يرجى المحاولة مرة أخرى.")
                            await send_whatsapp_message(from_number, error_message)

        print("=== WEBHOOK EVENT END ===\n")
        return JSONResponse(content={"status": "processed"})

    except Exception as e:
        print(f"Error in webhook: {str(e)}")
        traceback.print_exc()
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )

@app.get("/")
async def root():
    """Root endpoint - health check"""
    return {"message": "Kitchen Equipment Services Bot is running!"}

@app.get("/maintenance-requests/{request_id}")
async def get_maintenance_request(request_id: int, db: Session = Depends(get_db)):
    """Get a specific maintenance request"""
    request = DatabaseOperations.get_maintenance_request(db, request_id)
    if request is None:
        return JSONResponse(content={"error": "Request not found"}, status_code=404)
    return request

@app.on_event("startup")
async def startup_event():
    """Initialize database and clear sessions on startup"""
    try:
        # Initialize database
        init_db()
        print("Database initialized.")

        # Clear all existing sessions
        db = SessionLocal()
        try:
            # Delete all existing sessions
            db.query(CustomerSession).delete()
            db.commit()
            print("All existing sessions cleared.")
        except Exception as e:
            print(f"Error clearing sessions: {e}")
            db.rollback()
        finally:
            db.close()

        print("Application startup complete - ready to receive messages.")
    except Exception as e:
        print(f"Error during startup: {e}")

@app.post("/test/create-maintenance")
async def test_create_maintenance(db: Session = Depends(get_db)):
    """Test endpoint to create a maintenance request"""
    try:
        request_data = {
            "customer_name": "Test User",
            "phone_number": "+1234567890",
            "equipment_type": "cooking",
            "problem_description": "Test problem",
            "preferred_time": "Morning (9 AM - 12 PM)",
            "status": RequestStatus.PENDING.value,
            "photos": []
        }
        db_request = DatabaseOperations.create_maintenance_request(db, request_data)
        return {"status": "success", "request_id": db_request.id}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/test/maintenance-requests")    
async def test_list_maintenance(db: Session = Depends(get_db)):
    """Test endpoint to list all maintenance requests"""
    try:
        requests = db.query(MaintenanceRequest).all()
        return {"status": "success", "requests": requests}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/test/create-session")
async def test_create_session(db: Session = Depends(get_db)):
    """Test endpoint to create a customer session"""
    try:
        session_data = {
            "phone_number": "+1234567890",
            "session_data": {"state": "awaiting_name"},
            "language": "en"
        }
        db_session = DatabaseOperations.update_customer_session(
            db, 
            session_data["phone_number"], 
            session_data["session_data"],
            session_data["language"]
        )
        return {"status": "success", "session_id": db_session.id}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/database/health")
async def check_database(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))  # This should be fine
        return {"status": "connected"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/debug/session/{phone_number}")
async def debug_session(phone_number: str, db: Session = Depends(get_db)):
    """Debug endpoint to check current session state"""
    try:
        session = DatabaseOperations.get_customer_session(db, phone_number)
        if session:
            return {
                "status": "found",
                "language": session.language,
                "session_data": session.session_data
            }
        return {"status": "not_found"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/debug/check-request/{request_id}")
async def check_request(request_id: int, db: Session = Depends(get_db)):
    """Check details of a specific maintenance request"""
    try:
        request = db.query(MaintenanceRequest).filter(MaintenanceRequest.id == request_id).first()
        if request:
            return {
                "status": "found",
                "data": {
                    "id": request.id,
                    "customer_name": request.customer_name,
                    "phone_number": request.phone_number,
                    "equipment_type": request.equipment_type,
                    "problem_description": request.problem_description,
                    "preferred_time": request.preferred_time,
                    "status": request.status,
                    "created_at": request.created_at,
                    "photos": request.photos
                }
            }
        return {"status": "not_found", "message": f"No request found with ID {request_id}"}
    except Exception as e:
        print(f"Error checking request: {str(e)}")
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

@app.get("/debug/list-all-requests")
async def list_all_requests(db: Session = Depends(get_db)):
    """List all maintenance requests with detailed information"""
    try:
        requests = db.query(MaintenanceRequest).all()
        return {
            "status": "success",
            "total_count": len(requests),
            "requests": [
                {
                    "id": req.id,
                    "customer_name": req.customer_name,
                    "phone_number": req.phone_number,
                    "equipment_type": req.equipment_type,
                    "problem_description": req.problem_description,
                    "preferred_time": req.preferred_time,
                    "status": req.status,
                    "created_at": req.created_at,
                    "photos": req.photos
                }
                for req in requests
            ]
        }
    except Exception as e:
        print(f"Error listing requests: {str(e)}")
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

@app.get("/debug/maintenance-requests")
async def list_maintenance_requests(db: Session = Depends(get_db)):
    """List all maintenance requests in the database"""
    try:
        requests = db.query(MaintenanceRequest).all()
        return {
            "status": "success",
            "count": len(requests),
            "requests": [
                {
                    "id": request.id,
                    "customer_name": request.customer_name,
                    "phone_number": request.phone_number,
                    "equipment_type": request.equipment_type,
                    "problem_description": request.problem_description,
                    "preferred_time": request.preferred_time,
                    "status": request.status,
                    "created_at": request.created_at,
                    "photos": request.photos
                }
                for request in requests
            ]
        }
    except Exception as e:
        print(f"Error fetching maintenance requests: {str(e)}")
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

@app.get("/debug/reset-all")
async def reset_all_data(db: Session = Depends(get_db)):
    """Reset all sessions and maintenance requests - USE WITH CAUTION"""
    try:
        # Delete all sessions
        db.query(CustomerSession).delete()
        # Delete all maintenance requests
        db.query(MaintenanceRequest).delete()
        db.commit()
        return {"status": "success", "message": "All data reset successfully"}
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}

@app.get("/test/system-check")
async def system_check(db: Session = Depends(get_db)):
    try:
        results: Dict[str, Any] = {
            "database": False,
            "whatsapp_api": False,
            "session_management": False,
            "maintenance_system": False,
            "errors": {
                "database": None,
                "whatsapp_api": None,
                "session_management": None,
                "maintenance_system": None
            }
        }

        # Test database connection
        try:
            db.execute(text("SELECT 1"))
            results["database"] = True
        except Exception as e:
            results["errors"]["database"] = str(e)

        # Test WhatsApp API
        try:
            response = requests.get(
                f"https://graph.facebook.com/v17.0/{PHONE_NUMBER_ID}",
                headers={"Authorization": f"Bearer {ACCESS_TOKEN}"}
            )
            if response.status_code == 200:
                results["whatsapp_api"] = True
        except Exception as e:
            results["errors"]["whatsapp_api"] = str(e)

        # Test session management
        try:
            test_session = DatabaseOperations.update_customer_session(
                db, 
                "test_number",
                {"test": True},
                "en"
            )
            if test_session:
                DatabaseOperations.delete_customer_session(db, "test_number")
                results["session_management"] = True
        except Exception as e:
            results["session_management_error"] = str(e)

        # Test maintenance request system
        try:
            test_request = DatabaseOperations.create_maintenance_request(
                db,
                {
                    "customer_name": "Test User",
                    "phone_number": "test_number",
                    "equipment_type": "test",
                    "problem_description": "test",
                    "preferred_time": "test",
                    "status": RequestStatus.PENDING.value,
                    "photos": []
                }
            )
            if test_request:
                results["maintenance_system"] = True
        except Exception as e:
            results["maintenance_system_error"] = str(e)

        return {
            "status": "complete",
            "results": results
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

@app.get("/test/reset-session/{phone_number}")
async def reset_session(phone_number: str, db: Session = Depends(get_db)):
    """Reset a user's session"""
    try:
        DatabaseOperations.delete_customer_session(db, phone_number)
        return {"status": "success", "message": "Session reset successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/debug/maintenance-flow/{phone_number}")
async def debug_maintenance_flow(phone_number: str, db: Session = Depends(get_db)):
    """Debug endpoint to check maintenance flow state"""
    try:
        session = DatabaseOperations.get_customer_session(db, phone_number)
        if session:
            return {
                "status": "found",
                "language": session.language,
                "session_data": session.session_data,
                "current_state": session.session_data.get("state", "unknown")
            }
        return {"status": "not_found"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/maintenance/dashboard")
async def get_maintenance_dashboard(db: Session = Depends(get_db)):
    """Get organized maintenance request data with statistics"""
    try:
        # Get all requests
        requests = db.query(MaintenanceRequest).order_by(MaintenanceRequest.created_at.desc()).all()

        # Calculate statistics
        stats = {
            "total_requests": len(requests),
            "pending_requests": len([r for r in requests if r.status == "pending"]),
            "completed_requests": len([r for r in requests if r.status == "completed"]),
            "unique_customers": len(set(r.customer_name for r in requests)),
            "equipment_types": len(set(r.equipment_type for r in requests))
        }

        # Format requests data
        formatted_requests = [
            {
                "request_id": req.id,
                "customer": {
                    "name": req.customer_name,
                    "phone": req.phone_number
                },
                "equipment": {
                    "type": req.equipment_type,
                    "problem": req.problem_description
                },
                "schedule": {
                    "created_at": req.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "preferred_time": req.preferred_time
                },
                "status": req.status,
                "has_photos": bool(req.photos)
            }
            for req in requests
        ]

        return {
            "status": "success",
            "statistics": stats,
            "requests": formatted_requests
        }
    except Exception as e:
        print(f"Error getting dashboard data: {str(e)}")
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

@app.get("/maintenance/requests/{status}")
async def get_requests_by_status(status: str, db: Session = Depends(get_db)):
    """Get maintenance requests filtered by status"""
    try:
        requests = db.query(MaintenanceRequest)\
            .filter(MaintenanceRequest.status == status)\
            .order_by(MaintenanceRequest.created_at.desc())\
            .all()

        formatted_requests = [
            {
                "request_id": req.id,
                "customer": {
                    "name": req.customer_name,
                    "phone": req.phone_number
                },
                "equipment": {
                    "type": req.equipment_type,
                    "problem": req.problem_description
                },
                "schedule": {
                    "created_at": req.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "preferred_time": req.preferred_time
                },
                "status": req.status
            }
            for req in requests
        ]

        return {
            "status": "success",
            "count": len(requests),
            "requests": formatted_requests
        }
    except Exception as e:
        print(f"Error getting requests by status: {str(e)}")
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

@app.get("/test/supabase-connection")
async def test_supabase_connection(db: Session = Depends(get_db)):
    """Test the Supabase database connection and operations"""
    try:
        # 1. Test basic connection
        db.execute(text("SELECT 1"))
        print("Basic connection test passed")

        # 2. Test table creation
        init_db()
        print("Table creation test passed")

        # 3. Test data insertion
        test_request = DatabaseOperations.create_maintenance_request(
            db,
            {
                "customer_name": "Test Connection",
                "phone_number": "+1234567890",
                "equipment_type": "Test Equipment",
                "problem_description": "Testing Supabase Connection",
                "preferred_time": "Morning",
                "status": RequestStatus.PENDING.value,
                "photos": []
            }
        )
        print(f"Data insertion test passed. Created request with ID: {test_request.id}")

        # 4. Test data retrieval
        retrieved_request = DatabaseOperations.get_maintenance_request(db, test_request.id)
        print("Data retrieval test passed")

        return {
            "status": "success",
            "connection": "working",
            "tables_created": True,
            "test_data": {
                "id": retrieved_request.id,
                "name": retrieved_request.customer_name,
                "created_at": retrieved_request.created_at.isoformat()
            }
        }
    except Exception as e:
        print(f"Error in test_supabase_connection: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "message": str(e),
            "error_type": type(e).__name__
        }

# Also add a simpler test endpoint
@app.get("/test/db-ping")
async def test_db_ping(db: Session = Depends(get_db)):
    """Simple database connection test"""
    try:
        result = db.execute(text("SELECT 1")).scalar()
        return {
            "status": "success",
            "connection": "working",
            "ping_result": result
        }
    except Exception as e:
        print(f"Error in test_db_ping: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }

@app.get("/test/connection")
async def test_connection():
    """Test database connection and return detailed information"""
    try:
        # Get database version
        db = next(get_db())
        version = db.execute(text("SELECT version();")).scalar()

        # Test table creation
        Base.metadata.create_all(bind=engine)

        # Get table names
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        return {
            "status": "success",
            "database": "connected",
            "version": version,
            "tables": tables,
            "connection_url": SQLALCHEMY_DATABASE_URL.replace(
                "ZTk1PlGDMAW3omIM", "****"  # Hide password in response
            )
        }
    except Exception as e:
        print(f"Connection error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "message": str(e)
        }

@app.get("/test/create-tables")
async def create_tables():
    """Create database tables"""
    try:
        Base.metadata.create_all(bind=engine)
        return {"status": "success", "message": "Tables created successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/test/list-tables")
async def list_tables():
    """List all tables in the database"""
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        return {"status": "success", "tables": tables}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/test/diagnostic")
async def test_diagnostic(db: Session = Depends(get_db)):
    """Diagnostic test of database connection"""
    try:
        print("Testing database connection...")

        # Test 1: Basic Connection
        print("Test 1: Basic Connection")
        result = db.execute(text("SELECT current_database();")).scalar()
        print(f"Connected to database: {result}")

        # Test 2: List Tables
        print("Test 2: List Tables")
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        print(f"Found tables: {tables}")

        # Test 3: Create Test Record
        print("Test 3: Create Test Record")
        test_session = DatabaseOperations.update_customer_session(
            db,
            "test-diagnostic",
            {"test": True},
            "en"
        )
        print(f"Created test session with ID: {test_session.id}")

        return {
            "status": "success",
            "database_name": result,
            "tables": tables,
            "test_session_id": test_session.id
        }

    except Exception as e:
        print(f"Error in diagnostic: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "message": str(e),
            "type": type(e).__name__
        }

@app.get("/test/db-check")
async def test_db_check(db: Session = Depends(get_db)):
    """Comprehensive database connection test"""
    try:
        # Test 1: Basic connectivity
        db_version = db.execute(text("SELECT version();")).scalar()

        # Test 2: Create tables
        Base.metadata.create_all(bind=engine)

        # Test 3: Create a test maintenance request
        test_request = DatabaseOperations.create_maintenance_request(
            db,
            {
                "customer_name": "Test Connection",
                "phone_number": "+1234567890",
                "equipment_type": "Test Equipment",
                "problem_description": "Testing Database Connection",
                "preferred_time": "Morning",
                "status": RequestStatus.PENDING.value,
                "photos": []
            }
        )

        # Test 4: List all tables
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        return {
            "status": "success",
            "database_version": db_version,
            "tables_found": tables,
            "test_record_created": test_request.id,
            "connection_string": "postgresql://postgres.oblbsmcqjoyfpnrlaacm:****@aws-0-ap-south-1.pooler.supabase.com:6543/postgres"
        }
    except Exception as e:
        print(f"Database connection error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "message": str(e),
            "error_type": type(e).__name__,
            "connection_string": "postgresql://postgres.oblbsmcqjoyfpnrlaacm:****@aws-0-ap-south-1.pooler.supabase.com:6543/postgres"
        }

@app.get("/test/db-connection")
async def test_db_connection(db: Session = Depends(get_db)):
    """Test database connection"""
    try:
        # Attempt to query a simple value or count
        count = db.query(MaintenanceRequest).count()  # Replace with an actual model
        return {"status": "success", "message": f"Connected to database. Number of requests: {count}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

async def download_media(media_id: str) -> Optional[bytes]:
    """Download media from WhatsApp API"""
    try:
        # First, get the media URL
        url = f"https://graph.facebook.com/v17.0/{media_id}"
        headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}"
        }

        async with httpx.AsyncClient() as client:
            # Get media URL
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            media_data = response.json()

            if "url" not in media_data:
                print(f"No URL found in media data: {media_data}")
                return None

            # Download the actual media
            media_response = await client.get(
                media_data["url"],
                headers=headers
            )
            media_response.raise_for_status()

            return media_response.content

    except Exception as e:
        print(f"Error downloading media: {str(e)}")
        return None

# Add this endpoint to access photos
@app.get("/maintenance-requests/{request_id}/photos/{photo_index}")
async def get_request_photo(
    request_id: int,
    photo_index: int,
    db: Session = Depends(get_db)
):
    """Get a specific photo from a maintenance request"""
    try:
        # Get the request
        request = db.query(MaintenanceRequest).filter(MaintenanceRequest.id == request_id).first()
        if not request:
            return JSONResponse(
                content={"error": "Request not found"},
                status_code=404
            )

        # Check if photo exists
        if not request.photos or photo_index >= len(request.photos):
            return JSONResponse(
                content={"error": "Photo not found"},
                status_code=404
            )

        # Get the media ID
        media_id = request.photos[photo_index]

        # Download the photo
        photo_data = await download_media(media_id)
        if not photo_data:
            return JSONResponse(
                content={"error": "Could not download photo"},
                status_code=404
            )

        # Return the photo
        return Response(
            content=photo_data,
            media_type="image/jpeg"  # You might want to make this dynamic based on the actual image type
        )
    except Exception as e:
        print(f"Error getting photo: {str(e)}")
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )

# Add this endpoint to list all photos for a request
@app.get("/maintenance-requests/{request_id}/photos")
async def list_request_photos(request_id: int, db: Session = Depends(get_db)):
    """List all photos for a maintenance request"""
    try:
        request = db.query(MaintenanceRequest).filter(MaintenanceRequest.id == request_id).first()
        if not request:
            return JSONResponse(
                content={"error": "Request not found"},
                status_code=404
            )

        return {
            "request_id": request_id,
            "total_photos": len(request.photos) if request.photos else 0,
            "photo_ids": request.photos or []
        }

    except Exception as e:
        print(f"Error listing photos: {str(e)}")
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )

@app.get("/maintenance/photos/check/{request_id}")
async def check_photos_status(request_id: int, db: Session = Depends(get_db)):
    """Check status of photos for a maintenance request"""
    try:
        request = db.query(MaintenanceRequest).filter(MaintenanceRequest.id == request_id).first()
        if not request:
            return {
                "status": "error",
                "message": "Request not found"
            }

        results = []
        if request.photos:
            for i, photo_id in enumerate(request.photos):
                try:
                    # Test downloading each photo
                    photo_data = await download_media(photo_id)
                    results.append({
                        "index": i,
                        "media_id": photo_id,
                        "status": "available" if photo_data else "unavailable"
                    })
                except Exception as e:
                    results.append({
                        "index": i,
                        "media_id": photo_id,
                        "status": "error",
                        "error": str(e)
                    })

        return {
            "request_id": request_id,
            "total_photos": len(request.photos) if request.photos else 0,
            "photos": results
        }

    except Exception as e:
        print(f"Error checking photos: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)