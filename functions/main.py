# The Cloud Functions for Firebase SDK to create Cloud Functions and set up triggers.
from firebase_functions import firestore_fn, https_fn

# The Firebase Admin SDK to access Cloud Firestore.
from firebase_admin import initialize_app, firestore
import google.cloud.firestore
import json
from html import escape
from datetime import datetime

from jinja2 import Environment, FileSystemLoader
import os

import pytz

app = initialize_app()


def format_alert_html(problematic, safetywords, stringcheck, user, docid, all_responses):  
    """Format the HTML for safety alert emails using a Jinja2 template."""
    env = Environment(loader=FileSystemLoader(searchpath=os.path.dirname(__file__)))
    template = env.get_template('alert_template.html')
    
    # Get the current time
    est = pytz.timezone('US/Eastern')

    current_time = datetime.now(est).strftime("%Y-%m-%d %H:%M:%S")
    
    # Render the template with the current time
    return template.render(problematic=problematic, safetywords=safetywords, stringcheck=stringcheck, user=user, docid=docid, current_time=current_time, all_responses=all_responses)

@https_fn.on_request()
def fntester_add(req: https_fn.Request) -> https_fn.Response:
    """Take the text parameter passed to this HTTP endpoint and insert it into
    a new document in the fntester collection."""
    # Grab the text parameter.
    input_param_text = req.args.get("text")
    if input_param_text is None:
        input_param_text = "default value; No text parameter provided"

    firestore_client: google.cloud.firestore.Client = firestore.client()

    # Push the new message into Cloud Firestore using the Firebase Admin SDK.
    _, doc_ref = firestore_client.collection("fntester").add({
        "input_param_text": input_param_text,
        "surveyresponse": firestore_client.collection("surveyresponse").document("cj4zU5NjKjOvIkWG4JO0WLTnAb13_1725376398229").get().to_dict().get("surveyresponse"),
        "userid": "cj4zU5NjKjOvIkWG4JO0WLTnAb13"
    })

    # Send back a message that we've successfully written the message.
    return https_fn.Response(f"Messages with new ID {doc_ref.id} added.")


@firestore_fn.on_document_created(document="fntester/{pushId}")
def fntester_safety(event: firestore_fn.Event[firestore_fn.DocumentSnapshot | None]) -> None:
    """Listens for new documents to be added to /fntester. Checks for safety words in the survey response."""

    # Get the value of "surveyresponse" if it exists.
    if event.data is None:
        return "No data"

    try:
        surveyresp = event.data.get("surveyresponse")
        uid = event.data.get("userid")
    except:
        event.data.reference.update({"function_updates_safety_err": "Error - no surveyresponse found"})
        return "No data"

    firestore_client: google.cloud.firestore.Client = firestore.client()
    if uid:
        try:
            userdat = firestore_client.collection("users").document(uid).get().to_dict()
            event.data.reference.update({"user_snapshot": json.dumps(userdat)})
        except:
            event.data.reference.update({"function_updates_safety_err": f"Error - no user found {str(uid)}"})

    # Retrieve safety keywords
    safetywords = get_safety_keywords(firestore_client)

    # Extract text and "Other" responses from the survey
    responses = json.loads(surveyresp).get('results')
    all_responses = extract_text_and_other_responses(responses)

    # Convert all responses into a JSON string for alert purposes
    stringcheck = json.dumps(all_responses)

    # Run safety keyword checks
    # Run safety keyword checks
    safety_triggered_on = [
        {
            "question": response["question"],
            "response": response["response"],
            "matching_keywords": [safety_word for safety_word in safetywords if safety_word.casefold() in response["response"].casefold()]
        }
        for response in all_responses
        if any(safety_word.casefold() in response["response"].casefold() for safety_word in safetywords)
    ]


    if safety_triggered_on:
        html = format_alert_html(safety_triggered_on, safetywords, stringcheck, userdat, str(event.params['pushId']))

        event.data.reference.update({"alert": "ALERT: SAFETY CHECK TRIGGERED",
                                     "alert_sent_html": html,
                                     "safewords": str(safetywords),
                                     "function_updates_safety": "Alert: Safety check was triggered - please see email for details"})

        # Create a new document in the "mail" collection to trigger email
        mail_data = {
            "to": ["safety@edifii.me", "dev@edifii.me"],
            "message": {
                "subject": "Safety Check Alert Triggered",
                "html": html,
            }
        }
        firestore_client.collection("mail").add(mail_data)

        # Trigger SMS alert
        sms_data = {
            "to": ["+18777804236", "+16174602500"],
            "body": "Safety check was triggered - please see email for details"
        }
        firestore_client.collection("sms").add(sms_data)
    else:
        event.data.reference.update({"function_updates_safety": "No safety-check keywords found."})



"""Listens for new documents to be added to /surveyresponse. Checks for safety words in both text and 'Other' responses."""
@firestore_fn.on_document_created(document="surveyresponse/{pushId}")
def safetycheck(event: firestore_fn.Event[firestore_fn.DocumentSnapshot | None]) -> None:

    # Get the value of "surveyresponse" if it exists.
    if event.data is None:
        return "No data"

    try:
        surveyresp = event.data.get("surveyresponse")
        uid = event.data.get("userid")
    except:
        event.data.reference.update({"function_updates_safety_err": "Error - no surveyresponse found"})
        return "No data"

    firestore_client: google.cloud.firestore.Client = firestore.client()
    if uid:
        try:
            userdat = firestore_client.collection("users").document(uid).get().to_dict()
            event.data.reference.update({"user_snapshot": json.dumps(userdat)})
        except:
            event.data.reference.update({"function_updates_safety_err": f"Error - no user found {str(uid)}"})

    # Retrieve safety keywords
    safetywords = get_safety_keywords(firestore_client)

    # Extract text and "Other" responses from the survey
    responses = json.loads(surveyresp).get('results')
    all_responses = extract_text_and_other_responses(responses)

    # Convert all responses into a JSON string for alert purposes
    stringcheck = json.dumps(all_responses)

    # Run safety keyword checks
    safety_triggered_on = [
        {
            "question": response["question"],
            "response": response["response"],
            "matching_keywords": [safety_word for safety_word in safetywords if safety_word.casefold() in response["response"].casefold()]
        }
        for response in all_responses
        if any(safety_word.casefold() in response["response"].casefold() for safety_word in safetywords)
    ]

    if safety_triggered_on:
        html = format_alert_html(safety_triggered_on, safetywords, stringcheck, userdat, str(event.params['pushId']), all_responses)

        event.data.reference.update({"alert": "ALERT: SAFETY CHECK TRIGGERED",
                                     "alert_sent_html": html,
                                     "safewords": str(safetywords),
                                     "function_updates_safety": "Alert: Safety check was triggered - please see email for details"})

        # Create a new document in the "mail" collection to trigger email
        mail_data = {
            "to": ["safety@edifii.me"],
            "message": {
                "subject": "Survey Response Catchword Safety Alert",
                "html": html,
            }
        }
        firestore_client.collection("mail").add(mail_data)

        # Trigger SMS alert
        sms_data = {
            "to": ["+16174602500"],
            # "to": ["+16172753510"],
            "body": "Safety check was triggered - please see email for details"
        }
        firestore_client.collection("sms").add(sms_data)
    else:
        event.data.reference.update({"function_updates_safety": "No safety-check keywords found."})


def get_safety_keywords(firestore_client):
    """Retrieve the list of safety keywords from Firestore or use a default list."""
    try:
        return firestore_client.collection("function_params").document("safety_keywords").get().to_dict().get("trigger_safetycheck_any_match", [])
    except:
        return ['cut', 'harm', 'hurt', 'bleed', 'razor', 'pain', 'worthless', 'suicide', 'overdose', 
                'pills', 'drown', 'hang', 'starve', 'anorexia', 'bulimia', 'depression', 'depressed', 
                'alone', 'anxious', 'anxiety', 'die', 'death', 'lonely', 'hopeless', 'useless', 'blade', 
                'isolated', 'addiction', 'kill', 'murder', 'attack', 'stab', 'shoot', 'gun', 'knife', 
                'explode', 'bomb', 'revenge', 'hate', 'fight', 'violence', 'rage', 'assault', 'torture', 
                'strangle', 'bully', 'threaten', 'anger', 'hatred', 'angry', 'weapon', 'arson', 'abuse']


# def extract_text_and_other_responses(responses):
#     """Extract standard text responses and 'Other' values marked with isOther = true."""
#     text_responses = [item.get("result") for item in responses if item.get("step").get("answerFormat").get("type") == "text"]
#     other_responses = []
#     for item in responses:
#         if item.get("step").get("answerFormat").get("type") in ["single", "multi"]:
#             for choice in item.get("step").get("answerFormat").get("textChoices", []):
#                 if choice.get("isOther", False):
#                     if isinstance(item.get("result"), dict) and item.get("result").get("id") == choice.get("id"):
#                         other_responses.append(item.get("result").get("value"))
#                     elif isinstance(item.get("result"), list):
#                         for selected_choice in item.get("result"):
#                             if selected_choice.get("id") == choice.get("id"):
#                                 other_responses.append(selected_choice.get("value"))

#     return text_responses + other_responses

# def extract_text_and_other_responses(responses):
#     """Extract standard text responses and 'Other' values marked with isOther = true."""
#     extracted_responses = []
#     for item in responses:
#         answer_format = item.get("step", {}).get("answerFormat", {})
#         result = item.get("result")
        
#         if answer_format.get("type") == "text" and isinstance(result, str):
#             extracted_responses.append(result)
#         elif answer_format.get("type") in ["single", "multi"]:
#             text_choices = answer_format.get("textChoices", [])
#             for choice in text_choices:
#                 if choice.get("isOther", False):
#                     if isinstance(result, dict) and result.get("id") == choice.get("id"):
#                         other_value = result.get("value")
#                         if isinstance(other_value, str):
#                             extracted_responses.append(other_value)
#                     elif isinstance(result, list):
#                         for selected_choice in result:
#                             if selected_choice.get("id") == choice.get("id"):
#                                 other_value = selected_choice.get("value")
#                                 if isinstance(other_value, str):
#                                     extracted_responses.append(other_value)
#     return extracted_responses

def extract_text_and_other_responses(responses):
    """Extract question text and user responses."""
    extracted_responses = []
    for item in responses:
        answer_format = item.get("step", {}).get("answerFormat", {})
        question_text = answer_format.get("question", "N/A")

        result = item.get("result")
        
        if answer_format.get("type") == "text":
            extracted_responses.append({"question": question_text, "response": result.get("result")})
        elif answer_format.get("type") in ["single", "multi"]:
            text_choices = answer_format.get("textChoices", [])
            for choice in text_choices:
                if choice.get("isOther", False):
                    if isinstance(result, dict) and result.get("id") == choice.get("id"):
                        other_value = result.get("value")
                        if isinstance(other_value, str):
                            extracted_responses.append({"question": question_text, "response": other_value})
                    elif isinstance(result, list):
                        for selected_choice in result:
                            if selected_choice.get("id") == choice.get("id"):
                                other_value = selected_choice.get("value")
                                if isinstance(other_value, str):
                                    extracted_responses.append({"question": question_text, "response": other_value})
    return extracted_responses

# def format_alert_html(problematic, safetywords, stringcheck, user, docid):
#     """Format the HTML for safety alert emails."""
#     formatted_html = f"""
#     <div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; border: 1px solid #ccc; border-radius: 5px;">
#         <h2 style="color: #d9534f;">Safety Check Alert Triggered</h2>
#         <h3>User Information:</h3>
#         <p><strong>User Email:</strong> {escape(str(user.get('email', 'N/A')))}</p>
#         <p><strong>User ID:</strong> {escape(str(user.get('userid', 'N/A')))}</p>
#         <p><strong>Name:</strong> {escape(str(user.get('name', 'N/A')))}</p>
#         <p><strong>Grade:</strong> {escape(str(user.get('user_snapshot', 'N/A')))}</p>
#         <p><strong>Survey Response ID (firestore:surveyresponse):</strong> {escape(str(docid))}</p>
#         <h3>Problematic Responses:</h3>
#         <ul>
#             {"".join(f"<li>{escape(str(response))}</li>" for response in problematic)}
#         <h3>Alert Details:</h3>
#         <pre style="background-color: #f8f9fa; padding: 10px; border-radius: 5px;">{escape(str(stringcheck))}</pre>
#     </div>
#     """
#     return formatted_html
