# Import necessary libraries
import re
import uuid
from datetime import datetime
from autogen import UserProxyAgent
from zep_cloud.client import Zep
from zep_cloud import FactRatingExamples, FactRatingInstruction, Message
from llm_config import config_list
from prompt import agent_system_message, customer_support_system_message
from agent import ZepConversableAgent
from util import generate_user_id, load_support_knowledge_base
import streamlit as st


# Define zep as a global variable to be initialized later
zep = None


def initialize_zep_client(api_key):
    """Initialize the Zep client with the provided API key."""
    global zep
    try:
        zep = Zep(api_key=api_key)
        return True
    except Exception as e:
        st.error(f"Failed to initialize Zep Client: {e}")
        return False


def initialize_session(first_name, last_name, is_support_agent=False, ticket_id=None):
    """Initialize the session state and Zep connection."""
    # Check if we have a valid Zep client
    global zep
    if not zep:
        st.error("Zep client not initialized. Please enter a valid API key.")
        return

    if "zep_session_id" not in st.session_state or ticket_id:
        # Generate unique identifiers
        user_id = generate_user_id(first_name, last_name)
        
        # If this is for a support ticket, use the ticket ID as session ID
        session_id = ticket_id if ticket_id else str(uuid.uuid4())

        # Streamlit session state
        st.session_state.zep_session_id = session_id
        st.session_state.zep_user_id = user_id
        st.session_state.chat_initialized = False
        st.session_state.messages = []  # Store chat history for display
        st.session_state.is_support_mode = is_support_agent
        
        if ticket_id:
            st.session_state.ticket_id = ticket_id

        try:
            # Define fact rating instructions
            fact_rating_instruction = """Rate facts by relevance and utility. Highly relevant 
            facts directly impact the user's current needs or represent core preferences that 
            affect multiple interactions. Low relevance facts are incidental details that 
            rarely influence future conversations or decisions."""

            fact_rating_examples = FactRatingExamples(
                high="The user has had multiple issues with their account login in the past month.",
                medium="The user prefers email communication over phone calls.",
                low="The user mentioned they were using Chrome browser yesterday.",
            )

            # Attempt to add user
            user_exists = False
            try:
                # Try to get user
                zep.user.get(st.session_state.zep_user_id)
                user_exists = True
            except Exception:
                # User doesn't exist, create a new one
                zep.user.add(
                    first_name=first_name,
                    last_name=last_name,
                    user_id=st.session_state.zep_user_id,
                    fact_rating_instruction=FactRatingInstruction(
                        instruction=fact_rating_instruction,
                        examples=fact_rating_examples,
                    ),
                )

            # Add session for the user (whether new or existing)
            zep.memory.add_session(
                user_id=st.session_state.zep_user_id,
                session_id=st.session_state.zep_session_id,
            )

            # Show appropriate message
            if user_exists:
                st.sidebar.info(f"Using existing user: {st.session_state.zep_user_id}")
            else:
                st.sidebar.info(f"New user created for {first_name} {last_name}")

            st.session_state.chat_initialized = True
            st.sidebar.success("Zep user/session initialized successfully.")
            
            # Different welcome message for support mode
            if is_support_agent:
                welcome_msg = "Welcome to our Customer Support! 🎫 How can I assist you today?"
            else:
                welcome_msg = "Welcome! 😊 How can I assist you today?"
                
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": welcome_msg,
                }
            )

        # Handle any exceptions during initialization
        except Exception as e:
            st.error(f"Failed to initialize Zep user/session: {e}")
            st.stop()


def create_agents(is_support_mode=False):
    """Create and configure the conversational agents."""
    if st.session_state.chat_initialized:
        # Use the appropriate system message based on mode
        system_message = customer_support_system_message if is_support_mode else agent_system_message
        
        # Load knowledge base for customer support
        if is_support_mode:
            kb = load_support_knowledge_base()
            # Enhance system message with knowledge base if in support mode
            system_message = f"{system_message}\n\n## KNOWLEDGE BASE:\n{kb}"
        
        # Create the autogen agent with Zep memory
        agent = ZepConversableAgent(
            name="ZEP SUPPORT" if is_support_mode else "ZEP AGENT",
            system_message=system_message,
            llm_config={"config_list": config_list},
            zep_session_id=st.session_state.zep_session_id,
            zep_client=zep,
            min_fact_rating=0.7,
            function_map=None,
            human_input_mode="NEVER",
        )

        # Create UserProxy agent
        user = UserProxyAgent(
            name="UserProxy",
            human_input_mode="NEVER",
            max_consecutive_auto_reply=0,
            code_execution_config=False,
            llm_config=False,
        )

        return agent, user
    return None, None


def create_support_ticket(user_id, issue_title, issue_description):
    """Create a new support ticket and return the ticket ID."""
    # Generate a ticket ID with timestamp for uniqueness
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    ticket_id = f"TICKET-{timestamp}-{user_id[:5]}"
    
    # Store ticket metadata in Zep
    if zep:
        metadata = {
            "ticket_id": ticket_id,
            "created_at": datetime.now().isoformat(),
            "status": "open",
            "issue_title": issue_title,
            "issue_type": "customer_support",
        }
        
        # Create a new session for this ticket
        try:
            # Add session with metadata
            zep.memory.add_session(
                user_id=user_id,
                session_id=ticket_id,
                metadata=metadata
            )
            
            # Add the initial description as the first message
            zep.memory.add(
                session_id=ticket_id,
                messages=[
                    Message(
                        role_type="user",
                        role=user_id,
                        content=f"TICKET DESCRIPTION: {issue_description}",
                    )
                ]
            )
            
            return ticket_id
        except Exception as e:
            st.error(f"Failed to create ticket: {e}")
            return None
    return None


def get_user_tickets(user_id):
    """Retrieve all support tickets for a user."""
    if not zep:
        return []
        
    try:
        # Get all sessions for the user
        sessions = zep.memory.get_sessions(user_id)
        
        # Filter for support ticket sessions
        tickets = []
        for session in sessions:
            metadata = session.metadata
            if metadata and "ticket_id" in metadata and "issue_type" in metadata:
                if metadata["issue_type"] == "customer_support":
                    tickets.append({
                        "ticket_id": metadata["ticket_id"],
                        "created_at": metadata.get("created_at", "Unknown"),
                        "status": metadata.get("status", "open"),
                        "issue_title": metadata.get("issue_title", "Untitled Issue"),
                    })
        
        return tickets
    except Exception as e:
        st.error(f"Failed to retrieve tickets: {e}")
        return []


def update_ticket_status(ticket_id, new_status):
    """Update the status of a support ticket."""
    if not zep:
        return False
        
    try:
        # First get the current session to get existing metadata
        session = zep.memory.get_session(ticket_id)
        if not session or not session.metadata:
            return False
            
        # Update the status in metadata
        metadata = session.metadata
        metadata["status"] = new_status
        metadata["updated_at"] = datetime.now().isoformat()
        
        # Update the session with new metadata
        zep.memory.update_session(
            session_id=ticket_id,
            metadata=metadata
        )
        
        return True
    except Exception as e:
        st.error(f"Failed to update ticket status: {e}")
        return False


def handle_conversations(agent, user, prompt):
    """Process user input and generate assistant response."""
    # Add user message to display
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Append /no_think token for the backend processing
    prompt_with_token = f"{prompt} /no_think"

    # Store user's full name instead of ID
    user_full_name = f"{st.session_state.get('first_name', '')} {st.session_state.get('last_name', '')}".strip()

    # Use proper name if available, otherwise fall back to user ID
    display_name = user_full_name if user_full_name else st.session_state.zep_user_id

    # Persist user message and update system message with facts
    agent._zep_persist_user_message(prompt, user_name=display_name.upper())
    agent._zep_fetch_and_update_system_message()

    # Generate and display response
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("Thinking...")

        try:
            # Initiate chat with single turn
            user.initiate_chat(
                recipient=agent,
                message=prompt_with_token,
                max_turns=1,
                clear_history=False,
            )

            # Extract response from agent
            full_response = user.last_message(agent).get("content", "...")

            if not full_response or full_response == "...":
                full_response = "Sorry, I couldn't generate a response."

            # Remove <think> </think> tags from the response
            clean_response = re.sub(r'<think>.*?</think>', '', full_response, flags=re.DOTALL).strip()

            # Display the response
            message_placeholder.markdown(clean_response)

            # Add assistant response to display history
            st.session_state.messages.append(
                {"role": "assistant", "content": clean_response}
            )

        # Handle any exceptions during chat
        except Exception as e:
            error_message = f"Error during chat: {e}"
            raise RuntimeError(error_message) from e


def customer_support_view():
    """Render the customer support portal view."""
    st.title("🎫 Customer Support Portal")
    
    # Get user information
    if "zep_user_id" not in st.session_state:
        st.warning("Please enter your information to continue")
        return
    
    # Initialize tabs
    tab1, tab2, tab3 = st.tabs(["Create Ticket", "My Tickets", "Current Chat"])
    
    with tab1:
        st.header("Create New Support Ticket")
        issue_title = st.text_input("Issue Title", key="new_ticket_title")
        issue_description = st.text_area("Describe your issue", height=150, key="new_ticket_desc")
        
        if st.button("Submit Ticket"):
            if not issue_title or not issue_description:
                st.warning("Please fill out all fields")
            else:
                ticket_id = create_support_ticket(
                    st.session_state.zep_user_id, 
                    issue_title, 
                    issue_description
                )
                if ticket_id:
                    st.success(f"Ticket created successfully! ID: {ticket_id}")
                    st.session_state.new_ticket_created = ticket_id
                    # Reset the form fields
                    st.session_state.new_ticket_title = ""
                    st.session_state.new_ticket_desc = ""
                    
    with tab2:
        st.header("My Support Tickets")
        if st.button("Refresh Tickets"):
            st.session_state.tickets_refreshed = True
        
        # Get user's tickets
        tickets = get_user_tickets(st.session_state.zep_user_id)
        
        if tickets:
            # Create a DataFrame for better display
            ticket_data = []
            for ticket in tickets:
                # Format date for better readability
                created_date = ticket.get("created_at", "Unknown")
                if created_date != "Unknown":
                    try:
                        created_date = datetime.fromisoformat(created_date).strftime("%Y-%m-%d %H:%M")
                    except:
                        pass
                
                ticket_data.append({
                    "Ticket ID": ticket["ticket_id"],
                    "Created": created_date,
                    "Status": ticket["status"].upper(),
                    "Issue": ticket["issue_title"]
                })
            
            # Display tickets in a table
            import pandas as pd
            df = pd.DataFrame(ticket_data)
            st.dataframe(df, use_container_width=True)
            
            # Allow user to select a ticket to continue the conversation
            selected_ticket = st.selectbox(
                "Select a ticket to continue the conversation:", 
                options=[t["ticket_id"] for t in tickets],
                format_func=lambda x: f"{x} - {next((t['issue_title'] for t in tickets if t['ticket_id'] == x), '')}"
            )
            
            if st.button("Continue Conversation"):
                # Get user info from session state
                first_name = st.session_state.get("first_name", "")
                last_name = st.session_state.get("last_name", "")
                
                # Initialize a new session with the selected ticket ID
                initialize_session(first_name, last_name, is_support_agent=True, ticket_id=selected_ticket)
                st.session_state.active_tab = "Current Chat"
                st.experimental_rerun()
                
            # Allow user to close a ticket
            selected_ticket_to_close = st.selectbox(
                "Select a ticket to update:", 
                options=[t["ticket_id"] for t in tickets],
                format_func=lambda x: f"{x} - {next((t['issue_title'] for t in tickets if t['ticket_id'] == x), '')}",
                key="ticket_to_close"
            )
            
            new_status = st.selectbox(
                "New Status:", 
                options=["open", "closed", "resolved", "pending"],
                index=0
            )
            
            if st.button("Update Status"):
                if update_ticket_status(selected_ticket_to_close, new_status):
                    st.success(f"Ticket {selected_ticket_to_close} updated to {new_status}")
                    st.session_state.tickets_refreshed = True
                    st.experimental_rerun()
                else:
                    st.error("Failed to update ticket status")
        else:
            st.info("You don't have any support tickets yet.")
    
    with tab3:
        st.header("Support Conversation")
        if "chat_initialized" in st.session_state and st.session_state.chat_initialized:
            if "active_ticket" in st.session_state:
                st.info(f"Active Ticket: {st.session_state.active_ticket}")
            
            # Display chat history
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
            
            # Create support agent
            agent, user = create_agents(is_support_mode=True)
            
            # Handle user input
            if prompt := st.chat_input("Type your message here..."):
                handle_conversations(agent, user, prompt)
        else:
            st.info("Please select or create a ticket to start a conversation")


def main():
    """Main application entry point."""
    # Set page configuration
    st.set_page_config(
        page_title="Zep Memory Agent",
        page_icon="🧠",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Create a layout with columns for title and clear button
    col1, col2 = st.columns([5, 1])
    with col1:
        st.title("🧠 Zep Memory Agent")
        powered_by_html = """
    <div style='display: flex; align-items: center; gap: 10px; margin-top: 5px;'>
        <span style='font-size: 20px; color: #666;'>Powered by</span>
        <img src="https://files.buildwithfern.com/zep.docs.buildwithfern.com/2025-04-23T01:17:51.789Z/logo/zep-name-logo-pink.svg" width="100"> 
        <span style='font-size: 20px; color: #666;'>and</span>
        <img src="https://docs.ag2.ai/latest/assets/img/logo.svg" width="80">
    </div>
        """
        st.markdown(powered_by_html, unsafe_allow_html=True)

    # Clear chat history button
    with col2:
        if st.button("Clear ↺"):
            st.session_state.messages = []
            st.rerun()

    # Sidebar for API key, user information and controls
    with st.sidebar:
        # API Key input section
        zep_logo_html = """
        <div style='display: flex; align-items: center; gap: 10px; margin-top: 5px;'>
            <img src="https://files.buildwithfern.com/zep.docs.buildwithfern.com/2025-04-23T01:17:51.789Z/logo/zep-name-logo-pink.svg" width="100"> 
            <span style='font-size: 23px; color: #FFF; line-height: 1; display: flex; align-items: center; margin: 0;'>Configuration 🔑</span>
        </div>
        """
        st.markdown(zep_logo_html, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("[Get your API key](https://www.getzep.com/)", unsafe_allow_html=True)

        # Use session state to persist API key
        if "zep_api_key" not in st.session_state:
            st.session_state.zep_api_key = ""

        api_key = st.text_input(
            "Zep API Key",
            type="password",
            value=st.session_state.zep_api_key,
            help="Enter your Zep API key. This is required to use memory features.",
        )

        # Initialize Zep client when API key is provided
        if api_key:
            # Only initialize if the key has changed
            if api_key != st.session_state.zep_api_key or zep is None:
                if initialize_zep_client(api_key):
                    st.session_state.zep_api_key = api_key
                    st.success("✅ Zep client initialized successfully")
                else:
                    st.error("❌ Failed to initialize Zep client with provided key")
        else:
            st.warning("Please enter your Zep API key to continue!")

        # Only show user info section if Zep client is initialized
        if zep is not None:
            st.divider()
            st.header("👤 User Information")
            first_name = st.text_input("First Name", key="first_name")
            last_name = st.text_input("Last Name", key="last_name")

            # Add mode selection - regular assistant or customer support
            st.divider()
            app_mode = st.radio(
                "Select Mode:",
                ["Regular Assistant", "Customer Support"],
                key="app_mode"
            )
            
            # Different button text based on mode
            button_text = "Initialize Session ✅" if app_mode == "Regular Assistant" else "Enter Support Portal ✅"
            
            if st.button(button_text):
                if not first_name or not last_name:
                    st.warning("Please enter both first and last name")
                else:
                    # Initialize with appropriate mode
                    is_support_mode = (app_mode == "Customer Support")
                    initialize_session(first_name, last_name, is_support_agent=is_support_mode)
                    # Set mode in session state
                    st.session_state.is_support_mode = is_support_mode

            # Show session info if initialized
            if "zep_session_id" in st.session_state:
                st.divider()
                st.subheader("Session Details 🔽")
                st.info(f"Session ID: {st.session_state.zep_session_id[:8]}...")
                st.info(f"User ID: {st.session_state.zep_user_id}")
                if st.session_state.get("is_support_mode", False):
                    st.info("Mode: Customer Support")
                else:
                    st.info("Mode: Regular Assistant")

    # Determine which view to show based on mode
    if st.session_state.get("chat_initialized", False):
        if st.session_state.get("is_support_mode", False):
            customer_support_view()
        else:
            # Regular chat interface
            # Create agents
            agent, user = create_agents()
            if not agent or not user:
                st.error(
                    "Failed to create agents. Please check your autogen configuration."
                )
                return

            # Display chat history
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

            # Handle user input
            if prompt := st.chat_input("How are you feeling today?"):
                if not st.session_state.chat_initialized:
                    st.error("Chat not initialized yet. Try again.")
                    return

                handle_conversations(agent, user, prompt)
    else:
        if zep is not None:
            st.markdown("<br>", unsafe_allow_html=True)
            st.info(
                "Please enter your name and initialize a session to begin chatting 💬"
            )


# Run the Streamlit app
if __name__ == "__main__":
    main()