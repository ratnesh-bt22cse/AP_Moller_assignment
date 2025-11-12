import streamlit as st
import pandas as pd
import os
from dotenv import load_dotenv
from langgraph_agent import LangGraphEcommerceAgent
from datetime import datetime
import uuid

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="E-commerce AI Assistant (LangGraph)",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-title {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(120deg, #1f77b4, #ff7f0e);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }
    .subtitle {
        font-size: 1rem;
        color: #666;
        margin-bottom: 2rem;
    }
    .session-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 12px 16px;
        border-radius: 8px;
        margin: 8px 0;
        cursor: pointer;
        transition: transform 0.2s, box-shadow 0.2s;
        border: none;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .session-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    .session-title {
        font-size: 14px;
        font-weight: 600;
        margin-bottom: 4px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .session-meta {
        font-size: 11px;
        opacity: 0.9;
        display: flex;
        gap: 12px;
    }
    .stChatMessage {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'agent' not in st.session_state:
    st.session_state.agent = None
if 'session_id' not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'langgraph_messages' not in st.session_state:
    st.session_state.langgraph_messages = []
if 'initialized' not in st.session_state:
    st.session_state.initialized = False

# Sidebar
with st.sidebar:
    st.markdown("###  Configuration")
    
    # API key and DB path
    api_key = os.getenv("GEMINI_API_KEY")
    db_path = os.getenv("DB_PATH", "../data_structure/olist_master_clean.db")
    
    if api_key:
        st.success("✓ API Key loaded")
    else:
        st.error("✗ API Key not found")
    
    st.info(f" Database: {db_path}")
    
    # Initialize button
    if not st.session_state.initialized:
        if st.button(" Initialize LangGraph Agent", type="primary", use_container_width=True):
            if not api_key:
                st.error("Please set GEMINI_API_KEY in .env")
            else:
                full_db_path = os.path.join(os.path.dirname(__file__), db_path)
                
                if not os.path.exists(full_db_path):
                    st.error(f"Database not found: {full_db_path}")
                else:
                    try:
                        with st.spinner("Initializing LangGraph workflow..."):
                            st.session_state.agent = LangGraphEcommerceAgent(
                                full_db_path, 
                                api_key,
                                history_db="chat_history.db"
                            )
                            st.session_state.initialized = True
                            
                            # Add welcome message
                            welcome_msg = """

 """
                            
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": welcome_msg,
                                "timestamp": datetime.now()
                            })
                        
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
    else:
        st.success("✓ LangGraph Agent Active")
        
        # Show session info with context indicator
        session_info = f"📝 Session: {st.session_state.session_id[:8]}..."
        if len(st.session_state.messages) > 0:
            msg_count = len([m for m in st.session_state.messages if m['role'] == 'user'])
            session_info += f" | 💬 {msg_count} questions in context"
        st.info(session_info)
        
        # Session management
        st.divider()
        st.markdown("###  Session Management")
        
        # Enhanced new chat button styling
        st.markdown("""
            <style>
            .stButton > button {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                font-weight: 600;
                border: none;
                border-radius: 8px;
                padding: 0.6rem 1.2rem;
                transition: all 0.3s ease;
            }
            .stButton > button:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
            }
            </style>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("✨ New Chat", use_container_width=True):
                st.session_state.session_id = str(uuid.uuid4())
                st.session_state.messages = []
                st.session_state.langgraph_messages = []
                st.rerun()
        
        # with col2:
        #     if st.button(" Clear Chat", use_container_width=True):
        #         st.session_state.messages = []
        #         st.session_state.langgraph_messages = []
        #         st.rerun()
        
        # Session history
        if st.session_state.agent:
            st.divider()
            st.markdown("### 💬 Recent Conversations")
            
            sessions = st.session_state.agent.get_all_sessions()
            if sessions:
                for session in sessions[:10]:
                    session_name = session.get('session_name', 'Untitled Chat')
                    if not session_name or session_name == 'None':
                        session_name = 'Untitled Chat'
                    
                    # Format timestamp
                    from datetime import datetime
                    try:
                        last_active = datetime.fromisoformat(session['last_activity'])
                        time_str = last_active.strftime("%b %d, %I:%M %p")
                    except:
                        time_str = "Recently"
                    
                    # Create session card with load and delete buttons
                    col1, col2, col3 = st.columns([5, 1, 1])
                    with col1:
                        st.markdown(f"""
                        <div class="session-card">
                            <div class="session-title">💬 {session_name}</div>
                            <div class="session-meta">
                                <span>📅 {time_str}</span>
                                <span>💬 {session['message_count']} msgs</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with col2:
                        if st.button("📂", key=f"load_{session['session_id']}", help="Load this conversation"):
                            st.session_state.session_id = session['session_id']
                            # Load messages
                            history = st.session_state.agent.load_session_history(session['session_id'])
                            
                            # Restore display messages with re-execution of SQL queries
                            st.session_state.messages = []
                            for msg in history:
                                message_dict = {
                                    "role": msg['role'],
                                    "content": msg['content'],
                                    "sql": msg.get('sql_query'),
                                    "timestamp": msg['timestamp']
                                }
                                
                                # Re-execute SQL queries to restore data
                                if msg['role'] == 'assistant' and msg.get('sql_query'):
                                    try:
                                        # Re-run the SQL to get the data
                                        import pandas as pd
                                        data = pd.read_sql(msg['sql_query'], st.session_state.agent.conn)
                                        message_dict['data'] = data
                                    except:
                                        # If query fails, just show message without data
                                        message_dict['data'] = None
                                
                                st.session_state.messages.append(message_dict)
                            
                            # Restore LangGraph messages for context memory
                            from langchain_core.messages import HumanMessage, AIMessage
                            st.session_state.langgraph_messages = []
                            for msg in history:
                                if msg['role'] == 'user':
                                    st.session_state.langgraph_messages.append(
                                        HumanMessage(content=msg['content'])
                                    )
                                elif msg['role'] == 'assistant':
                                    st.session_state.langgraph_messages.append(
                                        AIMessage(content=msg['content'])
                                    )
                            
                            # Show success message
                            msg_count = len([m for m in history if m['role'] == 'user'])
                            st.success(f"✓ Loaded session with {msg_count} questions. Context restored!")
                            st.rerun()
                    
                    with col3:
                        # Simple delete button
                        if st.button("🗑️", key=f"delete_{session['session_id']}", help="Delete this conversation", type="secondary"):
                            # Check if it's the current session
                            if session['session_id'] == st.session_state.session_id:
                                st.toast("⚠️ Can't delete active session. Start a new chat first.", icon="⚠️")
                            else:
                                # Delete the session
                                if st.session_state.agent.delete_session(session['session_id']):
                                    st.toast(f"Deleted: {session_name}", icon="✅")
                                    st.rerun()
                                else:
                                    st.toast("Failed to delete session", icon="❌")
            else:
                st.info("💭 No previous conversations yet. Start chatting to create your first session!")
        
        # Stats
        if len(st.session_state.messages) > 0:
            st.divider()
            st.markdown("###  Current Session Stats")
            user_msgs = sum(1 for m in st.session_state.messages if m['role'] == 'user')
            st.metric("Questions Asked", user_msgs)
    
    # Sample questions
    st.divider()
    st.markdown("###  Sample Questions")
    
    samples = [
        "Top 5 states by sales?",
        "How many late orders?",
        "Avg review by category?",
        "Popular payment type?",
        "Revenue by month?",
    ]
    
    for sq in samples:
        if st.button(sq, key=f"sample_{sq}", use_container_width=True):
            if st.session_state.initialized:
                st.session_state.pending_question = sq
                st.rerun()
    
    # Schema viewer
    if st.session_state.agent:
        st.divider()
        with st.expander("Database Schema"):
            for table, columns in st.session_state.agent.schema.items():
                st.markdown(f"**{table}**")
                st.text(", ".join(columns))

# Main chat interface
st.markdown('<div class="main-title"> E-commerce AI Assistant</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle"></div>', unsafe_allow_html=True)

if not st.session_state.initialized:
    st.info("")
    
    # Show LangGraph architecture
    st.markdown("### ")
    st.markdown("""
    
    """)
else:
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            
            # Show SQL and results for assistant
            if message["role"] == "assistant" and message.get("sql"):
                with st.expander(" SQL Query"):
                    st.code(message["sql"], language="sql")
                
                if message.get("data") is not None:
                    data = message["data"]
                    if len(data) > 0:
                        st.dataframe(data, use_container_width=True)
                        
                        # Download button
                        csv = data.to_csv(index=False)
                        st.download_button(
                            label=" Download CSV",
                            data=csv,
                            file_name=f"results_{message['timestamp']}.csv",
                            mime="text/csv",
                            key=f"download_{message['timestamp']}"
                        )
    
    # Handle pending question from sample buttons
    if hasattr(st.session_state, 'pending_question'):
        prompt = st.session_state.pending_question
        delattr(st.session_state, 'pending_question')
    else:
        prompt = st.chat_input("Ask me anything about your e-commerce data...")
    
    # Process user input
    if prompt:
        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)
        
        st.session_state.messages.append({
            "role": "user",
            "content": prompt,
            "timestamp": datetime.now().isoformat()
        })
        
        # Process through LangGraph
        with st.chat_message("assistant"):
            with st.spinner("Processing through LangGraph workflow..."):
                result = st.session_state.agent.process_message(
                    user_message=prompt,
                    session_id=st.session_state.session_id,
                    existing_messages=st.session_state.langgraph_messages
                )
                
                # Update LangGraph message history
                from langchain_core.messages import HumanMessage, AIMessage
                st.session_state.langgraph_messages.append(HumanMessage(content=prompt))
                
                if result.success:
                    row_count = len(result.data)
                    
                    if row_count == 0:
                        response_text = "I found no results for your query."
                    elif row_count == 1 and len(result.data.columns) == 1:
                        value = result.data.iloc[0, 0]
                        response_text = f"**Answer:** {value}"
                    else:
                        response_text = f"Found **{row_count}** results:"
                    
                    st.markdown(response_text)
                    st.session_state.langgraph_messages.append(AIMessage(content=response_text))
                    
                    # Show SQL
                    if result.sql:
                        with st.expander("SQL Query"):
                            st.code(result.sql, language="sql")
                    
                    # Show results
                    if row_count > 0:
                        st.dataframe(result.data, use_container_width=True)
                        
                        csv = result.data.to_csv(index=False)
                        st.download_button(
                            label=" Download CSV",
                            data=csv,
                            file_name=f"results_{result.timestamp}.csv",
                            mime="text/csv"
                        )
                    
                    # Add to display messages
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": response_text,
                        "sql": result.sql,
                        "data": result.data,
                        "timestamp": result.timestamp
                    })
                else:
                    error_msg = f" Error: {result.error}"
                    st.error(error_msg)
                    st.session_state.langgraph_messages.append(AIMessage(content=error_msg))
                    
                    if result.sql:
                        with st.expander(" Generated SQL"):
                            st.code(result.sql, language="sql")
                    
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": error_msg,
                        "sql": result.sql,
                        "timestamp": result.timestamp
                    })

# Footer
st.divider()
st.caption("")
