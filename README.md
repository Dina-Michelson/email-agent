# Python Project Setup (Windows)

This section explains how to set up and run the project **on Windows**.

⚠️ **Important**

This project requires **Gmail API credentials** in order to send and modify emails.

You will need to place a credentials file in the project before running the application.
Instructions will be provided.

# 1. Clone the Repository

Open **PowerShell** or **Command Prompt** and run:

```bash
git clone https://github.com/Dina-Michelson/email-agent.git
```

---

# 2. Create a Python Virtual Environment

Create a virtual environment:

```bash
python -m venv venv
```

Activate it:

```bash
venv\Scripts\activate
```

After activation you should see `(venv)` at the start of your terminal line.

Example:

```
(venv) C:\projects\gmail-agent>
```

---

# 3. Install Project Dependencies

Install all required Python packages:

```bash
pip install -r requirements.txt
```

---

# 4. Environment Setup

The application uses environment variables to manage sensitive credentials. You must create a `.env` file in the root directory of the project with the following variables:

```bash
# Path to your Google Cloud credentials JSON file
GMAIL_CREDENTIALS_PATH=credentials/gmail_credentials.json

# Path where the OAuth2 token will be stored/read from
GMAIL_TOKEN_PATH=credentials/token.json

# Add your API key
OPENAI_API_KEY=your_openai_api_key_here 

OPENAI_MODEL="" #Optional the default in code is gpt4o
```

---

# 5. Add Gmail Credentials

Before running the project, place your Gmail OAuth credentials file in the following location:

```
credentials/gmail_credentials.json
```

Your project structure should look like this:

```
project-root
│
├── credentials
│   └── gmail_credentials.json
│
├── src
├── requirements.txt
└── README.md
```

If you do not yet have this file, follow the setup guide here:

➡️ **[Jump to Gmail Setup Instructions](#quick-gmail-setup)**

---

# 6. Run the Application

Run the program with:

```bash
python main.py
```

During the **first run**, a browser window will open asking you to authenticate with your Gmail account.

After you approve access, a token file will be created locally so you will not need to authenticate again.

---

# 7. Authentication Files

After the first successful login, the project will generate a file similar to:

```
credentials/token.json
```

This file stores your authentication session.

⚠️ Do **not commit this file to GitHub**.

Your `.gitignore` should include:

```
credentials/
.env
```

---

<a name="quick-gmail-setup"></a> 
# Quick Gmail Setup 

To allow the application to access **your Gmail account**, you must create Google Cloud credentials and enable the Gmail API.

---

## 1. Create a Google Cloud Project

1. Go to https://console.cloud.google.com/

2. Create a new project (example: `gmail-agent`)

3. Make sure the project is **selected**

---

## 2. Enable the Gmail API

Inside the project, use the **top search bar** and search:

```
Gmail API
```

Open it and click **Enable**.

---

## 3. Configure OAuth Consent Screen

Search in the top bar for:

```
OAuth consent screen
```

Configure it with:

```
User Type: External
App Name: anything
Support Email: your email
Developer Email: your email (Contact information)
```

Save and continue through the setup.

---

## 4. Add Required Scopes

Inside **OAuth Consent Screen → Data Access**, add the following scopes:

```
https://www.googleapis.com/auth/gmail.modify
https://www.googleapis.com/auth/gmail.send
```

Save changes.

---

## 5. Add Yourself as a Test User

Inside **OAuth Consent Screen → Audience**:

Add your Gmail address under **Test Users**.

Example:

```
test-user@gmail.com
```

Save.

---

## 6. Create OAuth Credentials

Search for **Credentials** in the top search bar.

Then:

```
Create Credentials → OAuth Client ID
Application Type → Desktop App
```

Name it anything (example: `gmail-agent-client`).

Click **Create**.

---

## 7. Download Credentials

Download the JSON file and place it in your project:

```
credentials/gmail_credentials.json
```

Example structure:

```
project-root/
│
├── credentials/
│   └── gmail_credentials.json
│
└── src/
```

---

✅ Gmail setup is complete.
You can now run the application and authenticate your Gmail account.

## Design Assumptions and Scope Limitations

This project focuses on the core requirements of the assessment: an agent that orchestrates Gmail searches, generates context-aware replies using an LLM, and manages the approval workflow. To maintain focus on the "agent-with-tools" architecture, the following design decisions and simplifications were made:

### 1. Email Attachments
The agent processes email metadata and body text only.
* **Decision:** Attachments are excluded from this implementation.
* **Reasoning:** Proper handling involves complex MIME parsing, binary storage, and security filtering which are outside the functional scope of this exercise.

### 2. Recipient Handling (CC / BCC)
The system defaults to replying to the primary sender while maintaining user control.
* **Decision:** While the agent identifies the original sender, the user is provided the opportunity to **modify the recipient** or the response before the final "send" action.
* **Reasoning:** This balances automation with safety, preventing accidental replies to large mailing lists or external domains.

### 3. Thread Context
The system is designed to handle threaded conversations.
* **Decision:** The agent retrieves and interprets the relevant message thread to ensure the suggested reply is contextually accurate.
* **Reasoning:** Providing the LLM with the conversation history significantly improves the quality and relevance of the generated draft.

### 4. LLM Context Window & Large Bodies
The implementation assumes the email content fits within the model's token limits.
* **Decision:** Advanced token management (such as recursive summarization or RAG-based chunking) is not implemented.
* **Reasoning:** For standard professional correspondence, modern LLM context windows are sufficient to demonstrate the agent's logic.

### 5. Sensitive Information & PII
The implementation assumes the environment is authorized for processing the provided email data.
* **Decision:** Automatic PII (Personally Identifiable Information) redaction or data masking is not included.
* **Reasoning:** In a production setting, the "human-in-the-loop" approval step implemented here serves as the primary safeguard.

### 6. No-Reply and Phishing Emails
The agent does not filter out no-reply senders or identify phishing attempts.
* **Decision:** Emails from addresses such as `no-reply@...` are processed the same as regular emails. No phishing detection or sender reputation checks are performed.
* **Reasoning:** Robust spam/phishing filtering and no-reply detection are infrastructure-level concerns (typically handled by the email provider) and are outside the scope of this exercise.

### 7. Duplicate Subjects
When multiple emails share the same subject line, only the most recent one is processed.
* **Decision:** If two or more emails have identical subjects, the agent selects the most recently received message and ignores the older ones.
* **Reasoning:** Processing duplicate threads would produce redundant or conflicting replies. Taking the latest message is the safest default while keeping the implementation simple.
