# CAMPUS CONNECT
## Product Requirements Document (PRD)

**Version:** 1.0  
**Project Type:** College Python Web Application  
**Primary Stack:** Python + Flask + SQLite + HTML/CSS/JavaScript

---

## 1. Project Overview

**Campus Connect** is a college web application that connects students and faculty in one academic communication and meeting-request platform.

The application solves a practical college problem: students may waste time trying to find faculty outside teaching hours or may use informal platforms such as WhatsApp for academic communication.

Campus Connect provides:
- Student and faculty accounts
- Academic profile management
- Faculty-student chat through Mentor-Connect
- Academic file sharing
- Faculty meeting requests
- Faculty-written meeting responses
- Supporting-faculty relationships
- In-app notifications
- Meeting and chat history
- Admin management and monitoring
- A data-driven scheduling research component

The application must remain simple, understandable, and deployable. It must not introduce features that are not specified in this document.

---

## 2. Problem Statement

Students need a reliable way to:
1. Contact the correct faculty member for academic doubts.
2. Ask for a faculty meeting without repeatedly searching for the faculty member.
3. Keep academic communication inside the college application.
4. Share project/assignment files.
5. Track meeting requests and previous meetings.

Faculty need a way to:
1. Communicate with students.
2. Respond to meeting requests at a time they choose.
3. Manage supporting-student relationships.
4. Maintain their profile through an approval-based process.

The project also needs to study whether different scheduling approaches can reduce student waiting time and improve meeting efficiency.

---

## 3. Project Goals

### Application Goals
- Provide a single academic communication platform.
- Keep student-faculty communication organized.
- Make meeting requests and responses traceable.
- Allow faculty to manually decide meeting timing.
- Provide controlled access based on academic relationships.
- Give administrators visibility into campus communication and meeting records.

### Research Goals
Compare:
1. FCFS/manual scheduling
2. Rule-based scheduling
3. Proposed intelligent/data-driven scheduling

using the same dataset and measurable metrics.

---

## 4. Roles

### 4.1 Student
A student can:
- Register and log in.
- Maintain a profile.
- View permitted faculty.
- Chat with permitted faculty through Mentor-Connect.
- Send PDF, image, and DOCX files.
- Edit a sent message only while it has not been seen by the recipient.
- Search faculty.
- Request a faculty meeting.
- Receive the faculty's written response and meeting timing.
- Cancel a meeting and provide a reason.
- Mark a meeting completed.
- View meeting history.
- View chat history.
- Request a supporting-faculty relationship.
- Receive notifications.
- Manage settings/theme.
- Upload or capture a profile picture.
- Request permission before changing any profile detail.

### 4.2 Faculty
A faculty member can:
- Register and log in.
- Maintain a profile.
- View assigned classes/sections and subjects.
- Chat with permitted students through Mentor-Connect.
- Send PDF, image, and DOCX files.
- Edit a sent message only while it has not been seen by the recipient.
- Search students by USN where the relationship rules permit it.
- Receive meeting requests.
- Accept or reject meeting requests.
- Enter meeting timing manually in the response.
- Cancel meetings.
- Mark meetings completed.
- View meeting history.
- Manage supporting-student relationships.
- Receive notifications.
- Upload or capture a profile picture.
- Request permission from admin before changing faculty details.

### 4.3 Admin
An admin can:
- Log in through the admin account.
- View student and faculty details.
- Manage campus/class data as permitted by the final implementation.
- View meeting records.
- View who met whom and when.
- View all chats.
- Review faculty profile/detail-change requests.
- Approve or reject faculty detail-change requests.
- Add new admins.
- Monitor the application.

There is **no public admin signup**. Admin accounts are created by an authorized existing admin/setup process.

---

## 5. Authentication and Registration

### Student Signup
1. Student enters college email.
2. System generates a random 6-digit demo OTP.
3. OTP is displayed on screen.
4. Student enters the OTP.
5. OTP is verified.
6. Student enters:
   - Full name
   - USN
   - Branch
   - Department
   - Year
   - Section
   - Phone
   - Personal email
   - College email
7. Student creates a new Campus Connect password.
8. Registration is completed.

The Campus Connect password is separate from the student's college email password.

### Faculty Signup
Faculty registration must collect the faculty information required by the application, including:
- Full name
- Faculty ID
- Department
- Subjects
- Professional email
- Assigned classes/sections as applicable
- Password
- Profile picture where provided

The exact faculty onboarding approval flow may be implemented according to the final institutional setup, but faculty accounts must not require storing a college email password.

### Login
Users log in with their Campus Connect credentials.

Passwords must be stored as secure password hashes, never as plain text.

---

## 6. Student Profile

Student profile fields:
- Full name
- USN
- Branch
- Department
- Year
- Section
- Phone
- Personal email
- College email
- Assigned/class faculty
- Profile picture

A student cannot directly change any profile detail.

**Change rule:**
> Student requests a change → Faculty reviews/approves → Student is allowed to make the approved change.

This applies to any student detail, including profile picture if the implementation treats it as a profile detail.

---

## 7. Faculty Profile

Faculty profile may contain:
- Full name
- Faculty ID
- Department
- Subjects
- Assigned classes/sections
- Professional email
- Profile picture

Faculty cannot directly change their details without the required approval.

**Change rule:**
> Faculty requests a change → Admin reviews → Admin approves/rejects → approved change can be made.

Admin must not directly edit faculty details as a shortcut.

---

## 8. Mentor-Connect

Mentor-Connect is the academic communication area.

### Student Side
A student sees permitted faculty and can open a conversation.

Students are restricted to:
- Their assigned/class faculty
- Approved supporting faculty

Supporting faculty is separate from the student's normal assigned faculty relationship.

### Faculty Side
Faculty can communicate with students who are permitted through the application's relationship rules.

### Chat Requirements
- Messages are stored as chat history.
- Unread message counts are shown.
- Messages cannot be deleted.
- A sender may edit their own message only until the recipient has seen it.
- Edited messages should be clearly marked as edited.
- Chat history remains available according to the application's access rules.
- Admin can view all chats.

### Attachments
Supported attachment types:
- PDF
- Images
- DOCX

The system must validate file type and handle uploads safely.

---

## 9. Faculty Search

Faculty search must support finding faculty by:
- Faculty ID
- Faculty name

Search is particularly important for creating supporting-faculty requests.

The application must not use search as a way to bypass normal student-faculty access restrictions.

---

## 10. Supporting Faculty

A student may request any faculty member to become a supporting faculty member by searching the faculty member's Faculty ID/name.

Flow:
1. Student searches faculty.
2. Student sends supporting-faculty request.
3. Faculty accepts or rejects.
4. If accepted, the faculty becomes an approved supporting faculty member for that student.
5. The relationship is then available for the permitted academic functions, including Mentor-Connect.

The relationship must be stored and have a clear status such as:
- Pending
- Accepted
- Rejected

A faculty member can similarly search for a student by USN and send a supporting-student request where allowed.

The student accepts/rejects the faculty's request.

---

## 11. Meeting Request System

There is **no fixed meeting duration** and **no fixed meeting time period**.

A student sends a meeting request to a permitted faculty member.

The request can contain:
- Reason/topic
- Message/details
- Request timestamp

### Faculty Response
Faculty manually responds to the request.

The faculty can:
- Accept
- Reject
- Provide meeting timing in free text

The timing is not generated from a mandatory booking calendar.

Example:
> "Come tomorrow at 2:30 PM."

The faculty's written response is stored with the meeting request.

### Meeting Statuses
Supported statuses:
- Pending
- Accepted
- Rejected
- Completed
- Cancelled

### Cancellation
Both student and faculty can cancel a meeting.

If the **student** cancels, the student must provide a cancellation reason.

The faculty cancellation flow should also record a reason where appropriate.

### Completion
Either student or faculty can mark a meeting as completed.

### Uncompleted Meetings
If neither person marks the meeting as Completed or Cancelled:
- The system continues sending reminder notifications.
- There is no automatic final expiration/no-show rule in the current requirements.
- Reminders continue until someone marks the meeting Completed or Cancelled.

### Meeting History
Meeting history must show relevant information such as:
- Student
- Faculty
- Request reason/topic
- Request date/time
- Faculty response
- Meeting timing
- Status
- Cancellation reason where applicable
- Completion information where applicable

---

## 12. Notifications

Notifications are **in-app only**.

Use notifications for events such as:
- New chat message
- New meeting request
- Meeting request accepted
- Meeting request rejected
- Faculty meeting response
- Supporting-faculty request
- Supporting-faculty request accepted/rejected
- Supporting-student request
- Permission request updates
- Meeting reminders
- Other important application events

Notifications should support unread/read state.

---

## 13. Scheduling Research Component

The project must answer:

> **Can data-driven scheduling reduce student waiting time and improve faculty-student meeting efficiency compared with the current/manual scheduling approach?**

### Data to Collect or Simulate
The research dataset should contain:
- Student meeting requests
- Faculty availability information when available for the experiment
- Class schedules
- Meeting duration
- Number of students requesting meetings
- Peak request periods
- Cancellations
- No-shows where represented in the experimental dataset

Important distinction:
- The live application does **not** assume that faculty's non-teaching or personal time is free.
- Faculty manually responds to live meeting requests.
- The research component may use explicitly defined availability data or simulated availability for controlled experiments.

### Scheduling Methods

#### Method 1: FCFS / Manual Baseline
Requests are handled in first-come, first-served order, representing the current/manual approach.

#### Method 2: Rule-Based Scheduling
Use explicit rules such as:
- Check faculty availability represented in the experiment.
- Check class schedules.
- Avoid existing meeting conflicts.
- Consider meeting duration.
- Select a valid conflict-free slot.

#### Method 3: Proposed Intelligent Scheduling
Use a simple data-driven scoring/optimization approach rather than unnecessary deep learning.

Potential factors:
- Request waiting time
- Request timestamp
- Meeting duration
- Faculty availability
- Class schedule
- Existing meetings
- Peak periods
- Cancellation/no-show patterns
- Fairness

The exact algorithm must be documented before implementation and evaluated against the same dataset as the other methods.

### Research Metrics
Compare:
- Average waiting time
- Minimum/maximum waiting time
- Number of successfully scheduled meetings
- Scheduling success rate
- Faculty idle time
- Schedule conflicts
- Cancellation/no-show rate
- Fairness among students

The comparison must use the same input data for all three methods.

---

## 14. UI/UX Requirements

Design must be:
- Simple
- Sleek
- Easy to understand
- Readable
- Responsive enough for normal browser use

### Color Direction
Primary visual language:
- Green shades
- Black
- White
- Neutral grey where needed

Do not use purple/violet as the main design language.

### Light Mode
- Light/white backgrounds
- Green accents and primary actions
- Dark/black readable text

### Dark Mode
- White areas become dark grey/grey
- Text and controls are adjusted for contrast
- Green remains an accent, not the entire interface

Green should not be used everywhere. It should mainly identify actions, active states, and important application accents.

---

## 15. Profile Pictures

Students and faculty can:
- Select a picture from their device
- Take a new picture using a camera where supported

Profile pictures are visible according to normal application access rules.

Suggested server storage:
- `uploads/profile/students/`
- `uploads/profile/faculty/`

The database stores the corresponding file path/reference.

---

## 16. Admin Visibility

Admin has broad monitoring access:
- Student details
- Faculty details
- Meeting records
- Meeting history
- Who met whom and when
- All chats

This is an explicit project requirement.

---

## 17. Out of Scope

Do not add these unless the requirements are explicitly changed later:
- Faculty announcements
- Public admin signup
- Email/SMS notification services
- Paid OTP services
- Storing college email passwords
- Mandatory faculty booking calendar
- Fixed meeting duration
- Automatic assumption that non-teaching time is available
- Automatic meeting-time assignment in the live application
- Message deletion
- Block/report system
- Unrequested social features
- Mobile application as a separate native app

---

## 18. Acceptance Criteria

The project is functionally complete when:

### Authentication
- Student can register using demo OTP and create an application password.
- Student/faculty can log in.
- Passwords are not stored in plain text.
- Admin login works without public admin signup.

### Student
- Student profile works.
- Faculty access follows relationship rules.
- Student can chat with permitted faculty.
- Student can send supported files.
- Student can request meetings.
- Student can see meeting status/history.
- Student can cancel with a reason.
- Student can mark meetings completed.
- Student can request supporting faculty.
- Student receives notifications.
- Student cannot change details without permission.

### Faculty
- Faculty profile works.
- Faculty can chat with permitted students.
- Faculty can receive/respond to meeting requests.
- Faculty can manually provide meeting timing.
- Faculty can accept/reject/cancel/complete meetings.
- Faculty can manage supporting-student requests.
- Faculty detail changes require admin approval.

### Admin
- Admin can see required user data.
- Admin can see all chats.
- Admin can see meeting history.
- Admin can approve/reject faculty detail-change requests.
- Admin can add admins.

### Scheduling Research
- Same dataset can be processed by all three scheduling approaches.
- Required metrics can be calculated.
- Results can be compared without changing the input data between methods.
- The experiment can demonstrate the measured differences clearly.

---

## 19. Source of Truth Rule

This PRD is the product-level source of truth.

When implementing Campus Connect:
1. Do not invent new features.
2. Do not silently remove a specified feature.
3. Do not change role permissions without updating the requirements.
4. Do not turn faculty's private/non-teaching time into automatic availability.
5. Do not introduce fixed meeting durations.
6. Do not introduce a booking calendar unless the requirements are changed.
7. Keep live manual faculty meeting responses separate from the research scheduling experiment.
8. If a requirement is technically ambiguous, stop and clarify before making a major architectural decision.


---

## Addendum: Academic hierarchy change

Class membership is now an Admin-controlled hierarchy: **Branch → Department → Academic Year →
Section** (default: branch CSE; departments AIML, AIDE, GenAI, Cybersecurity, Blockchain, IoT;
years 1st to 4th; sections A to C). Students choose their class once at registration and cannot
change it (Admin can remove the registration so the student re-registers). Faculty are no longer
tied to a single class faculty field: Admin assigns each faculty member to many sections (and a
section may have several faculty), or approves a faculty request to join a section. Student and
faculty reach each other only through an active class assignment or an accepted supporting-faculty
relationship. Details: `docs/ACADEMIC_HIERARCHY.md`.
