from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
import open_app
import search


class ActionOpenApp(Action):
    def name(self) -> Text:
        return 'action_open_app'
    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        appname = next(tracker.get_latest_entity_values("app_name"), None)
        if appname: # Add a check to ensure an appname was found
            print("Opening ", appname)
            dispatcher.utter_message(text=f"Opening {appname}.")
            open_app.launch_application_by_name(str(appname))
        else:
            print("Could not identify app name.")
            dispatcher.utter_message(text="Sorry, I couldn't identify the app you want to open.")
        return []
        
class ActionWebSearch(Action):
    def name(self) -> Text:
        return 'action_web_search'
    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        # Extract the search query from entities
        search_query = next(tracker.get_latest_entity_values("search_query"), None)
        
        # Pass the query to the search module's handle_search function
        # This function should handle all search logic including error handling and response formatting
        response = search.handle_search(search_query) if search_query else "I'm not sure what you want me to search for. Could you please be more specific?"
        
        # Display the response to the user
        dispatcher.utter_message(text=response)
        
        return []
