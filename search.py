import requests
import re
import datetime
import math
import operator
import wikipediaapi
import random
import string
from typing import List, Dict, Any, Tuple, Callable, Optional

# --- Query Classification ---

MATH_PATTERN = re.compile(r'^[\s\d\+\-\*\/\(\)\.\^\%\s]+$')
TIME_PATTERN = re.compile(r'(?i)(what|current|today).*?(time|date|day|month|year)')
WHO_PATTERN = re.compile(r'(?i)^who\s+(is|was|are|were)\s+')
WHAT_PATTERN = re.compile(r'(?i)^what\s+(is|are|was|were)\s+')
WHERE_PATTERN = re.compile(r'(?i)^where\s+(is|are)\s+')
WHEN_PATTERN = re.compile(r'(?i)^when\s+(is|was|did|will)\s+')
HOW_PATTERN = re.compile(r'(?i)^how\s+(do|does|did|to|can|could|would|should)\s+')

def classify_query(query: str) -> str:
    """
    Classify the query to determine the appropriate handler
    
    Args:
        query (str): The user's query
        
    Returns:
        str: Query type - 'math', 'time', 'wiki', 'ddg'
    """
    if not query:
        return 'unknown'
    
    # Check if it's a math expression
    if MATH_PATTERN.match(query.strip()):
        return 'math'
    
    # Check if it's a time/date query
    if TIME_PATTERN.search(query):
        return 'time'
    
    # Knowledge queries are best for Wikipedia
    if any(pattern.search(query) for pattern in [WHO_PATTERN, WHAT_PATTERN, WHERE_PATTERN, WHEN_PATTERN]):
        return 'wiki'
    
    # Default to DuckDuckGo for general queries
    return 'ddg'

# --- DuckDuckGo Handler ---

def ask_ddg(question: str) -> str:
    """
    Get information from DuckDuckGo Instant Answer API
    
    Args:
        question (str): The query to search for
        
    Returns:
        str: Search results or error message
    """
    url = "https://api.duckduckgo.com/"
    params = {
        "q": question,
        "format": "json",
        "no_html": 1,
        "skip_disambig": 1
    }

    response = requests.get(url, params=params)
    data = response.json()

    # Try abstract answer first
    if data.get("AbstractText"):
        return data["AbstractText"]

    # If no direct answer, try related topics
    related = data.get("RelatedTopics", [])
    if related:
        links = []
        for topic in related:
            if "Text" in topic and "FirstURL" in topic:
                links.append(f"{topic['Text']} - {topic['FirstURL']}")
            elif "Topics" in topic:
                for sub in topic["Topics"]:
                    if "Text" in sub and "FirstURL" in sub:
                        links.append(f"{sub['Text']} - {sub['FirstURL']}")
        return "\n".join(links[:3]) if links else "No links found."
    return "No answer or links found."

# --- Wikipedia Handler ---

def ask_wikipedia(query: str) -> str:
    """
    Get information from Wikipedia API
    
    Args:
        query (str): The query to search in Wikipedia
        
    Returns:
        str: Wikipedia summary or error message
    """
    # Use a proper user agent as required by Wikipedia's policy
    user_agent = "KettaAssistant/1.0 (https://github.com/your-repo/ketta; contact@example.com)"
    wiki_wiki = wikipediaapi.Wikipedia(
        language='en',
        extract_format=wikipediaapi.ExtractFormat.WIKI,
        user_agent=user_agent
    )
    
    # Clean up the query for better search results
    query = re.sub(r'(?i)^(who|what|where|when|how|why)\s+(is|are|was|were|do|does|did)\s+', '', query)
    query = query.strip()
    
    # Try to get a page by title
    page = wiki_wiki.page(query)
    
    if page.exists():
        # Get the summary (first 2 sentences)
        summary = page.summary.split('. ')
        result = '. '.join(summary[:2]) + '.'
        
        # Add a link to the full article
        result += f"\n\nRead more: {page.fullurl}"
        return result
    
    # If no direct match, try search suggestion
    search_query = query.replace(' ', '+')
    return f"I couldn't find specific information about that. Try looking at: https://en.wikipedia.org/w/index.php?search={search_query}"

# --- Math Expression Handler ---

def safe_eval(expr: str) -> str:
    """
    Safely evaluate a math expression
    
    Args:
        expr (str): Math expression string
        
    Returns:
        str: Result of the calculation or error message
    """
    # Clean the expression
    expr = expr.strip()
    
    # Simple validation to ensure it's a math expression
    if not MATH_PATTERN.match(expr):
        return "Sorry, I can only evaluate basic math expressions."
    
    # Replace ^ with ** for exponentiation
    expr = expr.replace('^', '**')
    
    try:
        # Use a simpler approach with direct eval but restrict the globals
        # This is still safe because we validated the input with MATH_PATTERN
        safe_globals = {
            '__builtins__': {
                'abs': abs,
                'float': float,
                'int': int,
                'pow': pow,
                'round': round
            },
            'math': math
        }
        
        # Calculate the result
        result = eval(expr, safe_globals)
        # Format the result nicely
        if isinstance(result, float):
            # Avoid scientific notation for small numbers, show reasonable decimal places
            if abs(result) < 1e-10:
                return "0"
            elif abs(result) < 1:
                return f"{result:.10f}".rstrip('0').rstrip('.')
            else:
                return f"{result:.6f}".rstrip('0').rstrip('.')
        return str(result)
    except Exception as e:
        return f"Sorry, I couldn't calculate that: {str(e)}"

# --- Time/Date Handler ---

def get_time_info(query: str) -> str:
    """
    Handle time and date queries
    
    Args:
        query (str): Time/date related query
        
    Returns:
        str: Current time/date information
    """
    now = datetime.datetime.now()
    
    if re.search(r'(?i)time', query):
        return f"The current time is {now.strftime('%I:%M %p')}."
    
    if re.search(r'(?i)date', query):
        return f"Today's date is {now.strftime('%A, %B %d, %Y')}."
    
    if re.search(r'(?i)day', query):
        return f"Today is {now.strftime('%A')}."
    
    if re.search(r'(?i)month', query):
        return f"The current month is {now.strftime('%B')}."
    
    if re.search(r'(?i)year', query):
        return f"The current year is {now.strftime('%Y')}."
    
    # Default comprehensive response
    return f"Today is {now.strftime('%A, %B %d, %Y')} and the current time is {now.strftime('%I:%M %p')}."

# --- Main Handler Function ---

def handle_search(search_query: str) -> str:
    """
    Main function to handle search requests
    
    Args:
        search_query (str): The query string to search for
        
    Returns:
        str: Formatted response with search results or error message
    """
    if not search_query:
        return "I'm not sure what you want me to search for. Could you please be more specific?"
    
    try:
        print(f"Searching for: {search_query}")
        
        # Classify the query
        query_type = classify_query(search_query)
        print(f"Query classified as: {query_type}")
        
        # Handle based on query type
        if query_type == 'math':
            result = safe_eval(search_query)
            return f"The result of the calculation is: {result}"
        
        elif query_type == 'time':
            result = get_time_info(search_query)
            return result
        
        elif query_type == 'wiki':
            result = ask_wikipedia(search_query)
            return f"Here's what I found:\n{result}"
        
        else:  # Default to DuckDuckGo
            initial_response = f"I'll search for information about '{search_query}'...\n\n"
            result = ask_ddg(search_query)
            
            if result:
                return initial_response + f"Here's what I found:\n{result}"
            else:
                # Fallback to Wikipedia if DuckDuckGo returns nothing
                wiki_result = ask_wikipedia(search_query)
                return initial_response + f"Here's what I found:\n{wiki_result}"
    
    except Exception as e:
        print(f"Error during search: {e}")
        return f"Sorry, I encountered an error while searching for '{search_query}'."
