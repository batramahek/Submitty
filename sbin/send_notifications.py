import json
import os
import datetime
from sqlalchemy import create_engine
import sys
import psutil

my_program_name = sys.argv[0]

my_pid = os.getpid()

# Loop over all active processes on the server
for p in psutil.pids():
    try:
        cmdline = psutil.Process(p).cmdline()
        if (len(cmdline) < 2):
            continue
        # If anything on the command line matches the name of the program
        if cmdline[0].find("python") != -1 and cmdline[1].find(my_program_name) != -1:
            if p != my_pid:
                print("ERROR!  Another copy of '" + my_program_name +
                      "' is already running on the server.  Exiting.")
                sys.exit(1)
    except psutil.NoSuchProcess:
        # Whoops, the process ended before we could look at it. But that's ok!
        pass

try:
    CONFIG_PATH = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), '..', 'config')

    with open(os.path.join(CONFIG_PATH, 'submitty.json')) as open_file:
        SUBMITTY_CONFIG = json.load(open_file)

    with open(os.path.join(CONFIG_PATH, 'database.json')) as open_file:
        DATABASE_CONFIG = json.load(open_file)

except Exception as config_fail_error:
    print("[{}] ERROR: CORE SUBMITTY CONFIGURATION ERROR {}".format(
        str(datetime.datetime.now()), str(config_fail_error)))
    sys.exit(1)


DATA_DIR_PATH = SUBMITTY_CONFIG['submitty_data_dir']
BASE_URL_PATH = SUBMITTY_CONFIG['submission_url']
NOTIFICATION_LOG_PATH = os.path.join(DATA_DIR_PATH, "logs", "notifications")
TODAY = datetime.datetime.now()
LOG_FILE = open(os.path.join(
    NOTIFICATION_LOG_PATH, "{:04d}{:02d}{:02d}.txt".format(TODAY.year, TODAY.month,
                                                    TODAY.day)), 'a')
try:
    DB_HOST = DATABASE_CONFIG['database_host']
    DB_USER = DATABASE_CONFIG['database_user']
    DB_PASSWORD = DATABASE_CONFIG['database_password']
except Exception as config_fail_error:
    e = "[{}] ERROR: Database Configuration Failed {}".format(
        str(datetime.datetime.now()), str(config_fail_error))
    LOG_FILE.write(e+"\n")
    print(e)
    sys.exit(1)

def connect_db(db_name):
    """Set up a connection with the database."""
    # If using a UNIX socket, have to specify a slightly different connection string
    if os.path.isdir(DB_HOST):
        conn_string = "postgresql://{}:{}@/{}?host={}".format(
            DB_USER, DB_PASSWORD, db_name, DB_HOST)
    else:
        conn_string = "postgresql://{}:{}@{}/{}".format(
            DB_USER, DB_PASSWORD, DB_HOST, db_name)

    engine = create_engine(conn_string)
    db = engine.connect()
    return db

def notifyPendingGradeables():
    master_db = connect_db("submitty")
    term = master_db.execute("SELECT term_id FROM terms WHERE start_date < NOW() AND end_date > NOW();")
    courses =  master_db.execute("SELECT term, course FROM courses WHERE term = '{}';".format(term.first()[0]))
    timestamp = str(datetime.datetime.now())

    for term, course in courses:
        course_db = connect_db("submitty_{}_{}".format(term, course))
        notified_gradeables = []
        
        gradeables = course_db.execute( """
            SELECT gradeable.g_id, gradeable.g_title FROM electronic_gradeable 
            JOIN gradeable ON gradeable.g_id =  electronic_gradeable.g_id
            WHERE gradeable.g_grade_released_date < NOW() AND electronic_gradeable.eg_student_view = true
            LIMIT 1;
        """)
                
        for row in gradeables:
            gradeable = { "id": row[0], "title": row[1] }
            
            # Construct gradeable URL into valid JSON string
            gradeable_url = "{}/courses/{}/{}/gradeable/{}".format(BASE_URL_PATH, term, course, gradeable["id"])
            metadata = json.dumps({ "url" : gradeable_url })
  
            # Send out notifications
            notification_list = []
            notification_content = "Grade Released: {}".format(gradeable["title"])
            
            if len(notification_content) > 40:
                # Max length for content of notification is 40
                notification_content = notification_content[:36] + "..."
            
            # user_group = 4 implies a student
            notification_recipients = course_db.execute("""
                SELECT users.user_id , users.user_email 
                FROM users
                JOIN notification_settings ON notification_settings.user_id = users.user_id 
                WHERE all_released_grades = true AND users.user_group = 4;
            """)
            
            for recipient in notification_recipients:
                user_id = recipient[0]
                notification_list.append("('grading', '{}', '{}', '{}', 'submitty-admin', '{}')".format(metadata, notification_content, timestamp, user_id))
            
            # Send notifications to all potential recipients 
            if len(notification_list) > 0:
                course_db.execute("INSERT INTO notifications(component, metadata, content, created_at, from_user_id, to_user_id) VALUES {};".format(', '.join(notification_list)))
      
            # Send out emails using both course and master database
            email_list = []
            email_subject = "[Submitty {}] Grade Released: {}".format(course, gradeable["title"])
            email_body = "An Instructor has released scores in:\n{}\nScores have been released for {}.\n\n".format(course, gradeable["title"]) + "Author: System\nClick here for more info: {}\n\n--\nNOTE: This is an automated email notification, which is unable to receive replies.\nPlease refer to the course syllabus for contact information for your teaching staff.".format(gradeable_url)     
            
            email_recipients = course_db.execute("""
                SELECT users.user_id , users.user_email 
                FROM users
                JOIN notification_settings ON notification_settings.user_id = users.user_id 
                WHERE notification_settings.all_released_grades_email = true AND users.user_group = 4;
            """ )
            
            for recipient in email_recipients:
                user_id, user_email = recipient[0], recipient[1]
                email_list.append("('{}', '{}', '{}', '{}', '{}', '{}', '{}')".format(email_subject, email_body, timestamp, user_id, user_email, term, course))
                
            if len(email_list) > 0:
                master_db.execute("INSERT INTO emails(subject, body, created, user_id, email_address, term, course) VALUES {};".format(', '.join(email_list)))
                            
            # Add successfully notified gradeables to eventually update notification state
            notified_gradeables.append("'{}'".format(gradeable["id"]))
            
        # Update all successfully sent notifications for current course
        if len(notified_gradeables) > 0:
            course_db.execute("UPDATE gradeable SET g_notification_state = true WHERE g_id in ({})".format(", ".join(notified_gradeables)))

        # Close the course database connection
        course_db.close()

def main():
    try:
        notifyPendingGradeables()
    except Exception as notification_send_error:
        e = "[{}] Error Sending Notification(s): {}".format(
            str(datetime.datetime.now()), str(notification_send_error))
        LOG_FILE.write(e+"\n")
        print(e)

if __name__ == "__main__":
    main()
