"""
context_bus.py
--------------
The "shared context bus" from the report. Instead of three agents working in
isolation, they all read from and write to this one object. That's what lets
the Teaching Agent's re-teach response refer to the exact question a student
missed, for example.

For this starter version the bus holds the current session state in memory
(which week we're on, the running conversation, and the student's weak topics)
and leans on database.py for anything that must persist between runs.
"""

from database import get_knowledge


class ContextBus:
    def __init__(self):
        self.current_week = 1
        self.current_resource_id = None  # active PDF resource row ID
        self.conversation = []   # list of {"role": ..., "content": ...}
        self.weak_topics = []    # concept tags the student has struggled with
        self.last_quiz_id = None

    # --- week / knowledge ---------------------------------------------------

    def set_week(self, week):
        self.current_week = int(week)

    def set_resource(self, resource_id: int, week: int):
        self.current_resource_id = int(resource_id)
        self.current_week = int(week)

    def knowledge_for_current_week(self):
        """Fetch the Research Agent's enriched material for the active week."""
        return get_knowledge(self.current_week)

    # --- conversation history ----------------------------------------------

    def add_message(self, role, content):
        self.conversation.append({"role": role, "content": content})

    def recent_conversation(self, limit=10):
        return self.conversation[-limit:]

    # --- weak topics --------------------------------------------------------

    def add_weak_topic(self, concept):
        if concept and concept not in self.weak_topics:
            self.weak_topics.append(concept)

    def clear(self):
        self.conversation = []
        self.weak_topics = []
        self.last_quiz_id = None


# A single shared instance the whole app imports and uses.
bus = ContextBus()
