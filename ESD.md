# CAMPUS CONNECT
## Engineering & System Design Document (ESD)

**Version:** 1.0  
**Project:** Campus Connect  
**Purpose:** Technical blueprint for implementing the PRD consistently and with minimal ambiguity.

---

# 1. Engineering Goal

Build a simple, fully functional, deployable college web application using:

- Python
- Flask
- SQLite
- HTML
- CSS
- JavaScript

The architecture should be understandable to a college project team and should avoid unnecessary complexity.

---

# 2. Recommended Architecture

```text
Browser
   |
   | HTTP / HTML / JSON
   v
Flask Application
   |
   +--------------------+
   |                    |
   v                    v
Business Logic       File Storage
   |
   v
SQLite Database
```

The application should be organized into logical modules rather than putting the entire project into one giant `app.py`.

---

# 3. Suggested Project Structure

```text
campus_connect/
│
├── app.py
├── config.py
├── requirements.txt
├── README.md
├── database.db
│
├── routes/
│   ├── auth.py
│   ├── student.py
│   ├── faculty.py
│   ├── admin.py
│   ├── chat.py
│   ├── meetings.py
│   ├── supporting.py
│   ├── notifications.py
│   └── scheduling.py
│
├── services/
│   ├── auth_service.py
│   ├── otp_service.py
│   ├── chat_service.py
│   ├── meeting_service.py
│   ├── notification_service.py
│   ├── permission_service.py
│   ├── file_service.py
│   └── scheduling/
│       ├── fcfs.py
│       ├── rule_based.py
│       ├── intelligent.py
│       ├── metrics.py
│       └── simulator.py
│
├── models/
│   ├── database.py
│   └── schema.py
│
├── templates/
│   ├── base.html
│   ├── auth/
│   ├── student/
│   ├── faculty/
│   └── admin/
│
├── static/
│   ├── css/
│   ├── js/
│   └── images/
│
└── uploads/
    ├── profile/
    │   ├── students/
    │   └── faculty/
    └── chat/
```

The exact folder names may change during implementation, but the separation of concerns must remain.

---

# 4. Core Roles

Use a role field on the user account.

Allowed roles:

```text
STUDENT
FACULTY
ADMIN
```

Do not create public registration for ADMIN.

An authorized setup/admin process creates admin accounts.

---

# 5. Database Design

SQLite is the recommended database.

Use foreign keys and appropriate indexes.

## 5.1 users

Purpose: authentication and common account data.

Suggested fields:

```text
id
role
email
password_hash
full_name
profile_picture_path
is_active
created_at
updated_at
```

Rules:
- `email` must be unique.
- `password_hash` must contain a hash, never the original password.
- `role` must be one of STUDENT/FACULTY/ADMIN.

---

## 5.2 students

Purpose: student-specific information.

Suggested fields:

```text
id
user_id
usn
branch
department
year
section
phone
personal_email
college_email
class_faculty_id
created_at
updated_at
```

Rules:
- `user_id` references `users.id`.
- `usn` should be unique.
- `class_faculty_id` references the assigned faculty relationship where applicable.

---

## 5.3 faculty

Purpose: faculty-specific information.

Suggested fields:

```text
id
user_id
faculty_id
department
professional_email
created_at
updated_at
```

Rules:
- `faculty_id` must be unique.
- `user_id` references `users.id`.

---

## 5.4 faculty_subjects

```text
id
faculty_id
subject_name
```

Allows one faculty member to have multiple subjects.

---

## 5.5 faculty_classes

```text
id
faculty_id
branch
department
year
section
```

Allows faculty to be associated with classes/sections.

---

## 5.6 otp_sessions

```text
id
email
otp_hash_or_value
expires_at
verified
created_at
attempt_count
```

For this college demo project, the random 6-digit OTP is displayed on screen.

Do not connect a paid OTP provider unless requirements change.

---

## 5.7 permission_requests

Use this table for profile/detail-change approval workflows.

Suggested fields:

```text
id
requester_user_id
target_approver_user_id
request_type
requested_changes
status
reason
created_at
reviewed_at
```

Statuses:

```text
PENDING
APPROVED
REJECTED
```

For students:
- requester = student
- approver = appropriate faculty

For faculty:
- requester = faculty
- approver = admin

Approved changes can then be applied.

---

## 5.8 chats

Suggested fields:

```text
id
student_id
faculty_id
created_at
updated_at
```

One logical conversation exists between a student and faculty member.

Access must follow the application's relationship rules.

---

## 5.9 messages

Suggested fields:

```text
id
chat_id
sender_user_id
message_text
attachment_path
attachment_type
is_seen
seen_at
is_edited
created_at
updated_at
```

Rules:
- Messages cannot be deleted.
- Sender may edit only before recipient has seen the message.
- Once seen, editing is rejected.
- `is_edited` becomes true after an edit.
- Attachments are optional.

---

## 5.10 supporting_relationships

Use a single relationship table.

Suggested fields:

```text
id
student_id
faculty_id
requested_by
status
created_at
updated_at
```

Statuses:

```text
PENDING
ACCEPTED
REJECTED
```

`requested_by` can identify whether the request came from student or faculty.

---

## 5.11 meeting_requests

Suggested fields:

```text
id
student_id
faculty_id
reason
student_message
faculty_response
meeting_time_text
status
requested_at
responded_at
completed_at
cancelled_at
cancelled_by
cancellation_reason
last_reminder_at
created_at
updated_at
```

Statuses:

```text
PENDING
ACCEPTED
REJECTED
COMPLETED
CANCELLED
```

Important:
- `meeting_time_text` is intentionally text, because faculty manually enters the timing.
- Do not force a fixed meeting duration.
- Do not require a calendar slot.
- The system should preserve the faculty's original response.

---

## 5.12 notifications

Suggested fields:

```text
id
user_id
notification_type
title
message
related_entity_type
related_entity_id
is_read
created_at
```

---

## 5.13 admin_accounts / admin audit data

Admin accounts can use the common `users` table with `role = ADMIN`.

If needed, add an admin-specific table for:
- created_by_admin
- created_at
- active status

Do not add unnecessary admin complexity unless required.

---

# 6. Relationships

Conceptually:

```text
USER
 ├── STUDENT
 │      ├── student profile
 │      ├── chats
 │      ├── meetings
 │      ├── supporting faculty
 │      └── permission requests
 │
 ├── FACULTY
 │      ├── faculty profile
 │      ├── chats
 │      ├── meetings
 │      ├── supporting students
 │      └── permission requests
 │
 └── ADMIN
        ├── monitors system
        ├── approves faculty changes
        └── creates admins
```

---

# 7. Authentication Design

## Passwords

Use a standard password hashing library supported by Flask/Python, such as Werkzeug's password hashing utilities.

Never:
- Store plain passwords.
- Store college email passwords.
- Ask for a user's existing college email password.

## Session

After successful login:
- Store user ID in the Flask session.
- Store role in session or retrieve it from the database.
- Protect role-specific routes.

Example:

```text
/student/*
/faculty/*
/admin/*
```

must check the user's role before serving the page.

---

# 8. Student Signup Flow

```text
Enter college email
       |
       v
Generate random 6-digit OTP
       |
       v
Display OTP on screen
       |
       v
Student enters OTP
       |
       v
Verify OTP
       |
       v
Enter student details
       |
       v
Create Campus Connect password
       |
       v
Create USER + STUDENT record
```

Validation must include:
- Required fields
- Unique USN
- Valid email format
- Password requirements
- OTP correctness
- OTP expiry

---

# 9. Faculty Signup Flow

Faculty enters required faculty information and creates a Campus Connect password.

Faculty ID must be unique.

If the final institutional process requires admin approval before faculty activation, implement the account as pending until approved.

Do not create a public admin signup flow.

---

# 10. Access Control

Access control must be checked server-side.

Do not rely only on hiding buttons in HTML.

## Student-to-Faculty Access

A student can access normal faculty communication when the faculty is:
1. Assigned/class faculty, or
2. Approved supporting faculty.

Faculty search may locate faculty for supporting requests, but searching must not automatically grant communication access.

## Faculty-to-Student Access

Faculty can access students according to their assigned/supporting relationship and the application's approved relationship rules.

## Admin

Admin has monitoring access to:
- Students
- Faculty
- Meetings
- Chats

---

# 11. Profile Change Approval

## Student

```text
Student wants any profile change
          |
          v
Create permission request
          |
          v
Faculty reviews
      /          Reject      Approve
    |            |
 No change    Allow requested change
```

The system should not silently modify data before approval.

## Faculty

```text
Faculty wants profile/detail change
          |
          v
Create permission request
          |
          v
Admin reviews
      /          Reject      Approve
    |            |
 No change    Allow requested change
```

---

# 12. Chat Design

A chat is identified by the student/faculty pair.

When opening a chat:
1. Verify relationship permission.
2. Load messages.
3. Mark eligible received messages as seen.
4. Update unread count.
5. Allow sending/editing according to rules.

## Message Edit Rule

```text
Sender sends message
       |
       v
Recipient has NOT seen it?
     /          YES        NO
   |           |
Edit allowed  Edit rejected
```

Never implement message deletion.

---

# 13. File Uploads

Supported:
- PDF
- JPG/JPEG/PNG and other explicitly allowed image formats
- DOCX

Recommended validation:
- Extension
- MIME/content type where practical
- Maximum file size
- Safe generated filename

Never use the original filename directly as the storage path.

Store files under:

```text
uploads/chat/
uploads/profile/students/
uploads/profile/faculty/
```

Store only the relative file path/reference in the database.

---

# 14. Meeting Request Architecture

## Student

```text
Select permitted faculty
        |
        v
Enter reason/topic
        |
        v
Send request
        |
        v
PENDING
```

## Faculty

```text
Receive request
      |
      +---- Reject
      |
      +---- Accept
              |
              v
      Enter meeting timing manually
              |
              v
           ACCEPTED
```

Faculty response fields:
- Response text
- Meeting timing text

Do not force:
- Calendar slot
- Fixed duration
- Availability calendar
- Automatic assignment

---

# 15. Meeting Cancellation

Student cancellation:

```text
Student selects Cancel
       |
       v
Require reason
       |
       v
Set CANCELLED
       |
       v
Notify faculty
```

Faculty cancellation:

```text
Faculty selects Cancel
       |
       v
Capture reason where applicable
       |
       v
Set CANCELLED
       |
       v
Notify student
```

Only valid active meetings can be cancelled.

---

# 16. Meeting Completion

Either student or faculty can select:

```text
Mark Completed
```

System:
- Changes status to `COMPLETED`
- Stores completion timestamp
- Stops further meeting reminders
- Creates notification/event if appropriate

---

# 17. Reminder System

Requirement:

> Keep reminding forever until someone marks Completed/Cancelled.

Therefore:
- Do not automatically mark a meeting as no-show.
- Do not automatically expire the meeting.
- Do not stop reminders merely because the meeting time has passed.

A scheduled background task can periodically find active meetings and send reminder notifications.

Example implementation options:
- Flask CLI scheduled task
- APScheduler
- Deployment cron/job

The exact interval can be configured.

Avoid duplicate reminders by using `last_reminder_at`.

---

# 18. Notification Architecture

Every important event should create a notification record.

Example:

```text
New meeting request
      |
      v
Create notification for faculty
```

Notification service should provide reusable functions such as:

```text
create_notification(...)
mark_notification_read(...)
get_unread_count(...)
```

Unread counts should be available for:
- Chat messages
- Notifications

---

# 19. Supporting Faculty Architecture

## Student Request

```text
Search faculty by Faculty ID/name
             |
             v
Send supporting request
             |
             v
Faculty receives notification
          /              Reject       Accept
```

If accepted:
- Create/activate relationship.
- Student can access permitted supporting-faculty features.

## Faculty Request

```text
Search student by USN
       |
       v
Send supporting-student request
       |
       v
Student receives notification
     /        Reject      Accept
```

Do not grant access before acceptance.

---

# 20. Faculty Search

Backend query should support:

```text
faculty_id
faculty_name
```

Use indexed fields where appropriate.

Search results must not expose unnecessary private information.

---

# 21. Admin Architecture

Admin dashboard should provide sections for:
- Students
- Faculty
- Meetings
- Chats
- Permission requests
- Admin management

Admin can:
- View all student/faculty details.
- View meeting records.
- View who met whom and when.
- View all chats.
- Approve/reject faculty detail changes.
- Add admins.

Admin must not bypass the faculty approval requirement by directly editing faculty details.

---

# 22. Scheduling Research Architecture

The research component should be separated from live meeting-request behavior.

```text
                Dataset
                   |
        +----------+----------+
        |          |          |
       FCFS      Rules    Intelligent
        |          |          |
        +----------+----------+
                   |
                Metrics
                   |
              Comparison
```

The same dataset must be passed to all three methods.

---

# 23. Research Dataset

Recommended fields:

```text
request_id
student_id_or_experiment_student_id
faculty_id
request_timestamp
faculty_availability
class_schedule
meeting_duration
peak_period
cancellation
no_show
```

Important:
- Synthetic experiment records may be generated for research.
- They must not be presented as fake real user accounts inside the application.
- Real application users and experimental data should remain conceptually separate.

---

# 24. FCFS Algorithm

Basic logic:

```text
1. Sort requests by request timestamp.
2. Process earliest request first.
3. Find the first valid slot according to the baseline assumptions.
4. Assign if possible.
5. Continue until all requests are processed.
```

Record:
- Assigned/unassigned
- Waiting time
- Conflicts
- Idle time
- Other required metrics

---

# 25. Rule-Based Algorithm

Use explicit deterministic rules.

Example:

```text
1. Sort/process requests.
2. Check faculty availability represented in the dataset.
3. Check class schedule conflicts.
4. Check existing meeting conflicts.
5. Consider meeting duration.
6. Find valid conflict-free slot.
7. Apply documented priority rules.
8. Record result.
```

Rules must be written down so the experiment is reproducible.

---

# 26. Intelligent Scheduling Algorithm

Do not add deep learning simply because the project says "intelligent."

Use a transparent scoring/optimization method.

Possible score factors:

```text
waiting time
request age
meeting duration
faculty availability
class conflict
existing meetings
peak period
cancellation/no-show history
fairness
```

A possible conceptual flow:

```text
Generate valid candidate slots
          |
          v
Remove conflicting slots
          |
          v
Score remaining candidates
          |
          v
Apply fairness constraints
          |
          v
Select best-scoring candidate
```

The exact formula must be documented before final evaluation.

---

# 27. Fairness

Fairness must not mean simply giving everyone the exact same priority.

The experiment should measure whether the algorithm repeatedly disadvantages particular students.

Useful measurements:
- Average waiting time per student
- Maximum waiting time
- Number of meetings served per student
- Distribution of service/waiting time

The fairness metric must be consistent across all three algorithms.

---

# 28. Research Metrics

For every scheduling method calculate:

### Waiting Time

```text
meeting_start_time - request_time
```

Use the same definition across all methods.

### Successful Scheduling

```text
scheduled_requests / total_requests
```

### Faculty Idle Time

Measure unused meeting-eligible periods represented in the experimental dataset.

### Conflicts

Count requests/assignments that violate defined scheduling constraints.

### Cancellation/No-Show Rate

Use the same cancellation/no-show definitions for all methods.

### Fairness

Use the chosen student-level distribution metric consistently.

---

# 29. Live App vs Research System

This distinction is critical.

## Live Application

```text
Student sends request
       |
       v
Faculty receives request
       |
       v
Faculty manually replies
       |
       v
Faculty enters timing
```

The live application does not automatically decide the meeting time.

## Research Experiment

```text
Experimental request dataset
          |
          v
FCFS / Rule-Based / Intelligent
          |
          v
Compare metrics
```

The research system can simulate scheduling decisions without changing the live application's manual faculty response model.

---

# 30. API/Route Plan

Suggested routes:

## Authentication

```text
GET  /login
POST /login
GET  /logout

GET  /signup/student
POST /signup/student
POST /signup/student/verify-otp

GET  /signup/faculty
POST /signup/faculty
```

## Student

```text
GET  /student/dashboard
GET  /student/profile
POST /student/profile/change-request
GET  /student/faculty/search
GET  /student/chats
GET  /student/chat/<id>
POST /student/chat/<id>/message
POST /student/message/<id>/edit
GET  /student/meetings
POST /student/meetings/request
POST /student/meetings/<id>/cancel
POST /student/meetings/<id>/complete
GET  /student/meetings/history
POST /student/supporting/request
POST /student/supporting/<id>/respond
GET  /student/notifications
```

## Faculty

```text
GET  /faculty/dashboard
GET  /faculty/profile
POST /faculty/profile/change-request
GET  /faculty/chats
GET  /faculty/chat/<id>
POST /faculty/chat/<id>/message
POST /faculty/message/<id>/edit
GET  /faculty/meetings
POST /faculty/meetings/<id>/accept
POST /faculty/meetings/<id>/reject
POST /faculty/meetings/<id>/cancel
POST /faculty/meetings/<id>/complete
GET  /faculty/meetings/history
POST /faculty/supporting/request
POST /faculty/supporting/<id>/respond
GET  /faculty/notifications
```

## Admin

```text
GET  /admin/dashboard
GET  /admin/students
GET  /admin/faculty
GET  /admin/meetings
GET  /admin/chats
GET  /admin/permission-requests
POST /admin/permission-requests/<id>/approve
POST /admin/permission-requests/<id>/reject
POST /admin/admins
```

Actual route names may differ, but functionality must remain equivalent.

---

# 31. Validation Rules

Every server-side operation must validate:
- Authentication
- Role
- Record ownership
- Relationship permissions
- Required fields
- Status transitions
- File type/size
- Unique identifiers
- Approval state

Never trust client-side JavaScript alone.

---

# 32. Meeting Status State Machine

Valid transitions:

```text
PENDING
  ├── ACCEPTED
  ├── REJECTED
  └── CANCELLED

ACCEPTED
  ├── COMPLETED
  └── CANCELLED

REJECTED
  └── terminal

COMPLETED
  └── terminal

CANCELLED
  └── terminal
```

Do not allow arbitrary status changes.

---

# 33. Permission Request State Machine

```text
PENDING
  ├── APPROVED
  └── REJECTED
```

Only the correct approver may decide.

---

# 34. Supporting Relationship State Machine

```text
PENDING
  ├── ACCEPTED
  └── REJECTED
```

Do not grant communication access while pending.

---

# 35. Error Handling

The application should provide understandable errors for:
- Invalid login
- Invalid OTP
- Expired OTP
- Duplicate USN
- Duplicate Faculty ID
- Unauthorized faculty access
- Unauthorized student access
- Invalid meeting state
- Editing a seen message
- Invalid file type
- File too large
- Missing cancellation reason
- Missing required meeting reason
- Unauthorized approval action

Do not expose raw database errors to normal users.

---

# 36. Security Baseline

This is a college project, but basic protections are required.

Implement:
- Password hashing
- Session-based authentication
- Server-side authorization
- CSRF protection where applicable
- Secure upload handling
- Filename sanitization/generated filenames
- Input validation
- Parameterized SQL / safe database access
- No password logging
- No college email password storage

---

# 37. Testing Plan

Test each role separately.

## Authentication
- Valid signup
- Invalid OTP
- Expired OTP
- Duplicate email
- Duplicate USN
- Duplicate Faculty ID
- Wrong password
- Logout

## Student
- Correct faculty access
- Unauthorized faculty access
- Chat
- Attachment upload
- Message edit before seen
- Message edit after seen
- Meeting request
- Cancellation reason
- Completion
- Supporting faculty request
- Profile change approval

## Faculty
- Meeting accept/reject
- Manual timing response
- Cancellation
- Completion
- Supporting-student request
- Student profile-change approval
- Faculty detail-change request

## Admin
- Login
- View students
- View faculty
- View meetings
- View chats
- Faculty change approval
- Add admin

## Scheduling
- Same dataset used by all methods
- Correct FCFS order
- Rule constraints
- Intelligent scoring
- Waiting-time calculation
- Conflict calculation
- Idle-time calculation
- Cancellation/no-show calculation
- Fairness calculation

---

# 38. Development Order

Build in this order to reduce integration errors:

```text
1. Project setup
2. Database schema
3. Authentication
4. Student/faculty profiles
5. Role-based access control
6. Student-faculty relationships
7. Mentor-Connect chat
8. File attachments
9. Notifications
10. Meeting requests
11. Meeting status/cancellation/completion
12. Supporting faculty
13. Permission approval workflows
14. Admin dashboard
15. Profile pictures
16. Theme/dark mode
17. Scheduling experiment data model
18. FCFS
19. Rule-based scheduling
20. Intelligent scheduling
21. Metrics and comparison
22. Testing
23. Deployment
```

Do not start with the intelligent scheduling algorithm before the basic application and data structures are stable.

---

# 39. Implementation Rules

These rules are mandatory for the project:

1. Do not invent features.
2. Do not remove approved requirements.
3. Do not change role permissions silently.
4. Do not make faculty non-teaching time automatically available.
5. Do not introduce fixed meeting duration.
6. Do not introduce a mandatory booking calendar.
7. Faculty manually enters meeting timing in the live app.
8. Keep research scheduling separate from live faculty decision-making.
9. Do not delete messages.
10. Do not allow editing after a message is seen.
11. Do not grant supporting-faculty access before acceptance.
12. Do not allow profile changes before required approval.
13. Do not allow students to change any profile detail without faculty approval.
14. Do not allow faculty to change profile details without admin approval.
15. Do not create public admin signup.
16. Do not store college email passwords.
17. Do not use paid OTP services for the demo.
18. Do not use fake application users as dummy profiles.
19. Synthetic scheduling experiment data is allowed, but must remain separate from fake application accounts.
20. All three scheduling methods must receive equivalent input data.
21. Any unclear requirement that can materially affect architecture must be clarified before implementation.

---

# 40. Deployment

The application should be deployable as a normal Flask web application.

Required project configuration:
- `requirements.txt`
- Environment/configuration file or environment variables where needed
- SQLite database initialization
- Upload directories
- Secret key configuration
- Production WSGI entry point where supported

Do not hard-code secrets.

SQLite is acceptable for the intended college project unless deployment requirements later require a server database.

---

# 41. Definition of Done

Campus Connect is ready when:

```text
Authentication works
        +
Roles work
        +
Profiles work
        +
Access rules work
        +
Chat works
        +
Files work
        +
Meeting workflow works
        +
Supporting faculty works
        +
Notifications work
        +
Approval workflows work
        +
Admin monitoring works
        +
Scheduling experiments work
        +
Metrics work
        +
Tests pass
        +
Deployment works
```

The implementation should be checked against both this ESD and the PRD before declaring the project complete.


---

## Addendum: Academic hierarchy change

New tables `branches`, `departments`, `academic_years`, `sections`, `faculty_assignments` and
`faculty_assignment_requests` (plus `students.section_id`) replace the free-text class columns and
the `faculty_classes` table for all access decisions; `login_attempts` and `users.last_login_at`
support login throttling. Data access lives in `models/academic_queries.py`; rules in
`services/academic_service.py` and `services/assignment_service.py`; the central check is
`is_student_in_faculty_scope`, used by chat, meeting, supporting-relationship, search and
profile-approval flows. Schema changes are applied additively and idempotently by
`models/database.init_db()`. See `DATABASE.md` and `docs/ACADEMIC_HIERARCHY.md`.
Deployment topology (Render backend with persistent disk, Vercel static + proxy frontend) is
described in `DEPLOYMENT.md`.
