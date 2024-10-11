from icalendar import Calendar
from datetime import datetime, timedelta
from num2words import num2words

from api import app


def __parse_ics_file__(ics_file_path):
    """
    Parses the .ics file and returns a list of events as dictionaries.

    Args:
        ics_file_path (str): Path to the .ics file.

    Returns:
        list: A list of dictionaries, each containing details of an event.
    """
    events = []

    try:
        # Open and read the .ics file
        with open(ics_file_path, 'rb') as f:
            ics_content = f.read()

        # Parse the .ics content
        calendar = Calendar.from_ical(ics_content)

        # Iterate through calendar components to find events
        for component in calendar.walk():
            if component.name == "VEVENT":
                # Get event details (summary, start time, end time, etc.)
                summary = component.get('summary', 'No title')
                start_time = component.get('dtstart').dt
                end_time = component.get('dtend').dt
                description = component.get('description', 'No description')
                location = component.get('location', 'No location')

                # Only process events with valid datetime objects
                if isinstance(start_time, datetime):
                    start_time_str = start_time.strftime('%Y-%m-%d %H:%M')
                else:
                    start_time_str = start_time

                if isinstance(end_time, datetime):
                    end_time_str = end_time.strftime('%Y-%m-%d %H:%M')
                else:
                    end_time_str = end_time

                # Create a dictionary for each event
                event = {
                    "summary": summary,
                    "start_time": start_time,
                    "end_time": end_time,
                    "location": location,
                    "description": description
                }

                # Append the event dictionary to the events list
                events.append(event)

    except FileNotFoundError:
        print(f"Error: File '{ics_file_path}' not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

    return events


def __convert_time_to_words__(time_obj):
    """
    Converts a time object (hours and minutes) into a human-readable string using num2words.

    Args:
        time_obj (datetime): A datetime object from which hours and minutes are extracted.

    Returns:
        str: The time in a human-readable format, e.g., "ten thirty".
    """
    hours = time_obj.hour
    minutes = time_obj.minute

    # Convert hours and minutes to words using num2words
    if hours == 0 and minutes == 0:
        return "midnight"
    elif hours == 12 and minutes == 0:
        return "noon"

    hours_in_words = num2words(hours)
    if minutes == 0:
        time_in_words = f"{hours_in_words} o'clock"
    else:
        minutes_in_words = num2words(minutes)
        time_in_words = f"{hours_in_words} {minutes_in_words}"

    return time_in_words


def __filter_events__(events, filter_type='all'):
    """
    Filters the events based on the filter_type (all, today, tomorrow, this_week).

    Args:
        events (list): List of event dictionaries.
        filter_type (str): Filter to apply (all, today, tomorrow, this_week).

    Returns:
        list: Filtered list of events.
    """
    filtered_events = []
    now = datetime.now()

    if filter_type == 'all':
        return events

    elif filter_type == 'today':
        for event in events:
            if isinstance(event['start_time'], datetime):
                event_date = event['start_time'].date()
                if event_date == now.date():
                    filtered_events.append(event)

    elif filter_type == 'tomorrow':
        tomorrow = now + timedelta(days=1)
        for event in events:
            if isinstance(event['start_time'], datetime):
                event_date = event['start_time'].date()
                if event_date == tomorrow.date():
                    filtered_events.append(event)

    elif filter_type == 'week':
        today = now.date()
        days_until_sunday = 6 - today.weekday()
        week_end = today + timedelta(days=days_until_sunday)
        for event in events:
            if isinstance(event['start_time'], datetime):
                event_date = event['start_time'].date()
                if today <= event_date <= week_end:
                    filtered_events.append(event)

    return filtered_events


def __generate_event_summary_string__(events, filter_type='all'):
    """
    Generates a natural language string summary for filtered events with creative language.

    Args:
        events (list): List of event dictionaries.
        filter_type (str): The filter type (e.g., 'today', 'this_week') to adjust phrasing.

    Returns:
        str: A natural language summary string describing the events.
    """
    if not events:
        return "There are no events."

    # Introductory phrase based on the filter type
    if filter_type == 'today':
        intro = "Today, you have the following events:\n"
    elif filter_type == 'tomorrow':
        intro = "Tomorrow, here are your planned events:\n"
    elif filter_type == 'week':
        intro = "This week, your schedule includes the following events:\n"
    else:
        intro = "Here are your upcoming events:\n"

    now = datetime.now()
    event_string = intro  # Initialize the event string with the introductory phrase

    # Iterate through the events to create a detailed summary
    for i, event in enumerate(events):
        event_summary = event.get("summary", "No title")
        start_time = event.get("start_time", "")

        if isinstance(start_time, datetime):
            event_day = start_time.strftime('%A')  # Get day of the week
            time_in_words = __convert_time_to_words__(start_time)  # Convert time to words
            days_until_event = (start_time.date() - now.date()).days  # How far away is the event

            # Creative phrasing based on how far away the event is
            if days_until_event == 0:
                phrase = f"{event_day} at {time_in_words}, you have {event_summary}."
            elif days_until_event == 1:
                phrase = f"tomorrow on {event_day} at {time_in_words}, {event_summary} is scheduled."
            elif days_until_event <= 3:
                phrase = f"later this week on {event_day} at {time_in_words}, you have {event_summary}"
            elif days_until_event == 4 or days_until_event == 5:
                phrase = f"as the week progresses, on {event_day} at {time_in_words}, you have {event_summary}."
            elif event_day in ['Saturday', 'Sunday']:
                phrase = f"at the end of the week, on {event_day} at {time_in_words}, you have {event_summary}"
            else:
                phrase = f"on {event_day} at {time_in_words}, {event_summary} is set."

            # Add "also" for additional events if applicable
            if i > 0 and i == len(events) - 1:
                phrase = f"And finally, {phrase}"
            elif i > 0:
                phrase = f"Also, {phrase}"

            # Add this event's string to the overall event string
            event_string += phrase + " "
        else:
            event_string += f"{event_summary} is scheduled, but the time isn't clear. "

    return event_string.strip()


def upcoming_events(**kwargs):
    events = __parse_ics_file__("/home/ilyamiro/.local/share/evolution/calendar/system/calendar.ics")
    for word in ["week", "tomorrow", "today"]:
        if word in kwargs["command"]:
            events_filtered = __filter_events__(events, word)
            string = __generate_event_summary_string__(events_filtered, word)
            print(string)
            app.say(string, prosody=88)
            break







