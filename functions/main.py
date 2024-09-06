# Welcome to Cloud Functions for Firebase for Python!
# To get started, simply uncomment the below code or create your own.
# Deploy with `firebase deploy`


# @https_fn.on_request()
# def on_request_example(req: https_fn.Request) -> https_fn.Response:
#     return https_fn.Response("Hello world!")


# The Cloud Functions for Firebase SDK to create Cloud Functions and set up triggers.
from firebase_functions import firestore_fn, https_fn

# The Firebase Admin SDK to access Cloud Firestore.
from firebase_admin import initialize_app, firestore
import google.cloud.firestore
import json
from html import escape

app = initialize_app()

@https_fn.on_request()
def fntester_add(req: https_fn.Request) -> https_fn.Response:
    """Take the text parameter passed to this HTTP endpoint and insert it into
    a new document in the messages collection."""
    # Grab the text parameter.
    input_param_text = req.args.get("text")
    if input_param_text is None:
        #return https_fn.Response("No text parameter provided", status=400)
        input_param_text = "default value; No text parameter provided"

    firestore_client: google.cloud.firestore.Client = firestore.client()

    # Push the new message into Cloud Firestore using the Firebase Admin SDK.
    _, doc_ref = firestore_client.collection("fntester").add({"input_param_text": input_param_text, 
                                                              "surveyresponse": firestore_client.collection("surveyresponse").document("cj4zU5NjKjOvIkWG4JO0WLTnAb13_1725376398229").get().to_dict().get("surveyresponse"),
                                                              "userid": "cj4zU5NjKjOvIkWG4JO0WLTnAb13"
                                                              })

    # Send back a message that we've successfully written the message and chet 
    return https_fn.Response(f"Messages with new ID {doc_ref.id} added.")



@firestore_fn.on_document_created(document="fntester/{pushId}")
def fntester_safety(event: firestore_fn.Event[firestore_fn.DocumentSnapshot | None]) -> None:
    """Listens for new documents to be added to /messages. If the document has
    an "surveyresp" field, checks if any safety word is in the surveyresp of text type."""

    # Get the value of "surveyresp" if it exists.
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
            userdat =  firestore_client.collection("users").document(uid).get().to_dict()
            event.data.reference.update({"user_snapshot": json.dumps(userdat) })
        except :
            # No "userdat" field, add error
            event.data.reference.update({"function_updates_safety_err": f"Error - no user found {str(uid)}"})

    try:
        safetywords =  firestore_client.collection("function_params").document("safety_keywords").get().to_dict().get("trigger_safetycheck_any_match")
        safetywords.append("Information___db_safety_keywordswords_used")
    except:
        # No "safetywords" found in firestore, so use backup
        safetywords = ['cut', 'harm', 'hurt', 'bleed', 'razor', 'pain', 'worthless', 'suicide', 'overdose', 
                       'pills', 'drown', 'hang', 'starve', 'anorexia', 'bulimia', 'depression', 'depressed', 
                       'alone', 'anxious', 'anxiety', 'die', 'death', 'lonely', 'hopeless', 'useless', 'blade', 
                       'isolated', 'addiction', 'kill', 'murder', 'attack', 'stab', 'shoot', 'gun', 'knife', 
                       'explode', 'bomb', 'revenge', 'hate', 'fight', 'violence', 'rage', 'assault', 'torture', 
                       'strangle', 'bully', 'threaten', 'anger', 'hatred', 'angry', 'weapon', 'arson', 'abuse', 
                       "Warning___default_safety_words_used"]


    ## Convert the json in surveyresp into a dict using json.loads and extract results 
    ## each item in the list is a dict - ['id', 'step', 'result', 'startTime', 'endTime']
    responses = json.loads(surveyresp).get('results') 

    # Step has ['id', 'isMandatory', 'isIntermediate', 'answerFormat', 'buttonText', 'content']
    # Result has variable type like direct string for "text" answer vs single choice: 
    # ['id', 'text', 'score', 'metric', 'dimension', 'scoreStart', 'scoreMode'] vs list of choices
    # get all the text input type questions together in a list of docts and later extract from within dict
    text_responses = [item for item in responses if item.get("step").get("answerFormat").get("type") == "text"]

    # Get all the text entered by user into one string
    stringcheck = json.dumps([each_input.get("result") for each_input in text_responses ])

    safety_triggered_on = []
    for response in text_responses:
        if any(safety_word.casefold() in response.get('result').casefold() for safety_word in safetywords):
            safety_triggered_on.append(response)
    
    if safety_triggered_on:
        html = ""
        for problematic in safety_triggered_on:
            html+=format_alert_html(problematic, safetywords, stringcheck, userdat, str(event.params['pushId']))
        
        event.data.reference.update({"alert": "ALERT: SAFETY CHECK TRIGGERED", 
                                     "alert_sent_html": html,
                                     "safewords": str(safetywords),
                                     "function_updates_safety": "Alert: Safety check was triggered - please see email for details"
                                       })
        
        # Create a new document in the "mail" collection to trigger email
        mail_data = {
            "to": ["safety@edifii.me","dev@edifii.me"],
            "message": {
                "subject": "Survey Response Catchword Safety Alert",
                "html": html, 
            }   
        }
        firestore_client.collection("mail").add(mail_data)

        sms_data = {
                    "to": ["+18777804236","+16174602500"],
                    "body": "Safety check was triggered - please see email for details"
                }
        firestore_client.collection("sms").add(sms_data)

    else:
        event.data.reference.update({"function_updates_safety": "No safety-check keywords found."})




@firestore_fn.on_document_created(document="surveyresponse/{pushId}")
def safetycheck(event: firestore_fn.Event[firestore_fn.DocumentSnapshot | None]) -> None:
    """Listens for new documents to be added to /messages. If the document has
    an "surveyresp" field, checks if any safety word is in the surveyresp of text type."""

    # Get the value of "surveyresp" if it exists.
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
            userdat =  firestore_client.collection("users").document(uid).get().to_dict()
            event.data.reference.update({"user_snapshot": json.dumps(userdat) })
        except :
            # No "userdat" field, add error
            event.data.reference.update({"function_updates_safety_err": f"Error - no user found {str(uid)}"})

    try:
        safetywords =  firestore_client.collection("function_params").document("safety_keywords").get().to_dict().get("trigger_safetycheck_any_match")
        safetywords.append("Information___db_safety_keywordswords_used")
    except:
        # No "safetywords" found in firestore, so use backup
        safetywords = ['cut', 'harm', 'hurt', 'bleed', 'razor', 'pain', 'worthless', 'suicide', 'overdose', 
                       'pills', 'drown', 'hang', 'starve', 'anorexia', 'bulimia', 'depression', 'depressed', 
                       'alone', 'anxious', 'anxiety', 'die', 'death', 'lonely', 'hopeless', 'useless', 'blade', 
                       'isolated', 'addiction', 'kill', 'murder', 'attack', 'stab', 'shoot', 'gun', 'knife', 
                       'explode', 'bomb', 'revenge', 'hate', 'fight', 'violence', 'rage', 'assault', 'torture', 
                       'strangle', 'bully', 'threaten', 'anger', 'hatred', 'angry', 'weapon', 'arson', 'abuse', 
                       "Warning___default_safety_words_used"]


    ## Convert the json in surveyresp into a dict using json.loads and extract results 
    ## each item in the list is a dict - ['id', 'step', 'result', 'startTime', 'endTime']
    responses = json.loads(surveyresp).get('results') 

    # Step has ['id', 'isMandatory', 'isIntermediate', 'answerFormat', 'buttonText', 'content']
    # Result has variable type like direct string for "text" answer vs single choice: 
    # ['id', 'text', 'score', 'metric', 'dimension', 'scoreStart', 'scoreMode'] vs list of choices
    # get all the text input type questions together in a list of docts and later extract from within dict
    text_responses = [item for item in responses if item.get("step").get("answerFormat").get("type") == "text"]

    # Get all the text entered by user into one string
    stringcheck = json.dumps([each_input.get("result") for each_input in text_responses ])

    safety_triggered_on = []
    for response in text_responses:
        if any(safety_word.casefold() in response.get('result').casefold() for safety_word in safetywords):
            safety_triggered_on.append(response)
    
    if safety_triggered_on:
        html = ""
        for problematic in safety_triggered_on:
            html+=format_alert_html(problematic, safetywords, stringcheck, userdat, str(event.params['pushId']))
        
        event.data.reference.update({"alert": "ALERT: SAFETY CHECK TRIGGERED", 
                                     "alert_sent_html": html,
                                     "safewords": str(safetywords),
                                     "function_updates_safety": "Alert: Safety check was triggered - please see email for details"
                                       })
        
        # Create a new document in the "mail" collection to trigger email
        mail_data = {
            "to": ["safety@edifii.me","dev@edifii.me"],
            "message": {
                "subject": "Survey Response Catchword Safety Alert",
                "html": html, 
            }   
        }
        firestore_client.collection("mail").add(mail_data)

        sms_data = {
                    "to": "+16174602500",
                    "body": "Safety check was triggered - please see email for details"
                }
        firestore_client.collection("sms").add(sms_data)

    else:
        event.data.reference.update({"function_updates_safety": "No safety-check keywords found."})


def format_alert_html(problematic: dict, safetywords: list, stringcheck: list, user: dict, docid: str = 'N/A') -> str:
    # Extract information from the problematic dictionary
    user_input = escape(str(problematic.get('result', '')))
    question_id = escape(str(problematic.get('id', '')))
    question_text = json.dumps([content.get('text', '') for content in problematic.get('step', {}).get('content', [])], ensure_ascii=False)
    question_text = escape(question_text)
    
    # Extract user information
    user_email = escape(str(user.get('email', 'N/A')))
    user_id = escape(str(user.get('userid', 'N/A')))
    
    # Ensure docid is a string and escape it
    docid = escape(str(docid))
    
    # Format the HTML string
    formatted_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; border: 1px solid #ccc; border-radius: 5px;">
        <h2 style="color: #d9534f;">Safety Check Alert Triggered</h2>
        <h3>User Information:</h3>
        <p><strong>User Email:</strong> {user_email}</p>
        <p><strong>User ID:</strong> {user_id}</p>
        <p><strong>Survey Response ID (firestore:surveyresponse):</strong> {docid}</p>
        <h3>Alert Details:</h3>
        <p><strong>User Input:</strong> <span style="color: #d9534f;">{user_input}</span></p>
        <p><strong>Question ID:</strong> {question_id}</p>
        <p><strong>Question Text:</strong> {question_text}</p>
        <p><strong>Safety Check Words:</strong> {escape(str(safetywords))}</p>
        <h3>All Text-Based User Responses in the Survey:</h3>
        <pre style="background-color: #f8f9fa; padding: 10px; border-radius: 5px;">{escape(str(stringcheck))}</pre>
    </div>
    """
    
    return formatted_html