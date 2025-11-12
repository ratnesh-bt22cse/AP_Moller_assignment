# LANGGRAPH-BASED E-COMMERCE AGENT WITH STATE MANAGEMENT

import os
import sqlite3
import pandas as pd
from datetime import datetime
from typing import TypedDict, Annotated, List, Dict, Any
from dataclasses import dataclass
import json

from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
import re


@dataclass
class QueryResult:
    """Data class for query results"""
    question: str
    sql: str
    data: pd.DataFrame
    success: bool
    error: str = None
    timestamp: str = None


class ConversationState(TypedDict):
    """State definition for the conversation graph"""
    messages: Annotated[List, "The conversation messages"]
    database_path: str
    database_schema: Dict[str, List[str]]
    last_sql: str
    last_result: pd.DataFrame
    session_id: str
    query_count: int
    error: str


class LangGraphEcommerceAgent:
    """LangGraph-based E-commerce Agent with persistent state and history"""
    
    def __init__(self, db_path: str, api_key: str, history_db: str = "chat_history.db"):
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database not found at {db_path}")
        
        if not api_key or api_key.strip() == "":
            raise ValueError("Please provide a valid Gemini API key!")
        
        self.db_path = db_path
        self.history_db_path = history_db
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        
        # Initialize LangChain Gemini model
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=api_key,
            temperature=0.1,
            top_p=0.8,
            top_k=40,
        )
        
        # Load database schema
        self.schema = self._get_schema()
        
        # Initialize chat history storage
        self._init_history_db()
        
        # Build the conversation graph
        self.graph = self._build_graph()
        
        print(f"LangGraph Agent initialized with {len(self.schema)} tables")
    
    def _get_schema(self) -> Dict[str, List[str]]:
        """Get database schema"""
        schema = {}
        tables_query = "SELECT name FROM sqlite_master WHERE type='table';"
        tables = pd.read_sql(tables_query, self.conn)['name'].tolist()
        
        for table in tables:
            cols = pd.read_sql(f"PRAGMA table_info({table});", self.conn)
            schema[table] = cols['name'].tolist()
        
        return schema
    
    def _init_history_db(self):
        """Initialize SQLite database for chat history"""
        history_conn = sqlite3.connect(self.history_db_path)
        cursor = history_conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id TEXT PRIMARY KEY,
                session_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                role TEXT,
                content TEXT,
                sql_query TEXT,
                result_count INTEGER,
                success BOOLEAN,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
            )
        """)
        
        history_conn.commit()
        history_conn.close()
        print(f"Chat history database initialized: {self.history_db_path}")
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph conversation workflow"""
        
        # Define the graph
        workflow = StateGraph(ConversationState)
        
        # Add nodes
        workflow.add_node("understand_query", self._understand_query_node)
        workflow.add_node("generate_sql", self._generate_sql_node)
        workflow.add_node("execute_query", self._execute_query_node)
        workflow.add_node("format_response", self._format_response_node)
        workflow.add_node("handle_error", self._handle_error_node)
        
        # Add edges
        workflow.set_entry_point("understand_query")
        
        workflow.add_conditional_edges(
            "understand_query",
            self._should_generate_sql,
            {
                "generate": "generate_sql",
                "error": "handle_error"
            }
        )
        
        workflow.add_conditional_edges(
            "generate_sql",
            self._check_sql_valid,
            {
                "valid": "execute_query",
                "invalid": "handle_error"
            }
        )
        
        workflow.add_conditional_edges(
            "execute_query",
            self._check_execution,
            {
                "success": "format_response",
                "error": "handle_error"
            }
        )
        
        workflow.add_edge("format_response", END)
        workflow.add_edge("handle_error", END)
        
        return workflow.compile()
    
    # Graph Nodes
    
    def _understand_query_node(self, state: ConversationState) -> ConversationState:
        """Node: Understand user query and context"""
        messages = state["messages"]
        
        # Get the last user message
        user_message = messages[-1] if messages else None
        
        if not user_message or not isinstance(user_message, HumanMessage):
            state["error"] = "No valid user message found"
            return state
        
        # Build context from previous messages
        context = self._build_context(messages[:-1])
        state["context"] = context
        
        return state
    
    def _generate_sql_node(self, state: ConversationState) -> ConversationState:
        """Node: Generate SQL using LLM"""
        messages = state["messages"]
        user_query = messages[-1].content
        
        # Build schema text
        schema_text = "\n".join(
            [f"Table: {t}\nColumns: {', '.join(c)}" for t, c in state["database_schema"].items()]
        )
        
        # Build conversation context with previous SQL queries
        context_text = ""
        if len(messages) > 1:
            recent_msgs = [msg for msg in messages[-8:-1] if not isinstance(msg, SystemMessage)]
            if recent_msgs:
                context_text = "\n\nRecent Conversation Context (for follow-up questions):\n"
                for i, msg in enumerate(recent_msgs):
                    role = "User" if isinstance(msg, HumanMessage) else "Assistant"
                    content = msg.content[:150]
                    context_text += f"{role} #{i+1}: {content}...\n"
                
                # Add the last SQL query if available
                if state.get("last_sql"):
                    context_text += f"\nLast SQL Query: {state['last_sql']}\n"
                context_text += "\nIMPORTANT: If the user's question refers to 'those', 'that', 'them', 'these results', use the context above to understand what they're referring to.\n"
        
        # Create prompt with context
        prompt_text = f"""You are an expert SQL generator for SQLite databases with conversational awareness.

Database Schema:
{schema_text}
{context_text}

CRITICAL RULES:
1. Output ONLY a valid SQLite SELECT statement
2. Do NOT include markdown, backticks, or explanations
3. Use only tables and columns from the schema above
4. The main table is 'olist_master' (use this table for all queries)
5. For aggregations, use GROUP BY
6. Round decimals to 2 places: ROUND(column, 2)
7. CONVERSATIONAL MEMORY: If user refers to previous results/questions, analyze the conversation context above
8. For follow-up questions like "what about those?", "show me more details", modify or extend the previous query
9. Output format: SELECT ... FROM ... WHERE ... GROUP BY ... ORDER BY ... LIMIT ...

Current User Question: "{user_query}"

Generate ONLY the SQL query:"""
        
        try:
            # Call LLM with HumanMessage (Gemini requires at least one non-system message)
            response = self.llm.invoke([HumanMessage(content=prompt_text)])
            sql = response.content.strip()
            
            # Clean the SQL
            sql = re.sub(r'```sql\s*', '', sql)
            sql = re.sub(r'```\s*', '', sql)
            sql = re.sub(r'^sql\s*', '', sql, flags=re.IGNORECASE)
            sql = sql.strip().rstrip(';').strip()
            sql = ' '.join(sql.split())
            
            state["last_sql"] = sql
            
        except Exception as e:
            state["error"] = f"SQL generation failed: {str(e)}"
        
        return state
    
    def _execute_query_node(self, state: ConversationState) -> ConversationState:
        """Node: Execute the SQL query"""
        sql = state.get("last_sql")
        
        if not sql:
            state["error"] = "No SQL to execute"
            return state
        
        try:
            result_df = pd.read_sql(sql, self.conn)
            state["last_result"] = result_df
            state["query_count"] = state.get("query_count", 0) + 1
            
        except Exception as e:
            state["error"] = f"Query execution failed: {str(e)}"
        
        return state
    
    def _format_response_node(self, state: ConversationState) -> ConversationState:
        """Node: Format the response for the user"""
        result_df = state.get("last_result")
        
        if result_df is None:
            state["error"] = "No results to format"
            return state
        
        # Create a response message
        row_count = len(result_df)
        
        if row_count == 0:
            response_text = "I found no results for your query."
        elif row_count == 1 and len(result_df.columns) == 1:
            value = result_df.iloc[0, 0]
            response_text = f"The answer is: {value}"
        else:
            response_text = f"I found {row_count} results for your query."
        
        # Add AI message to conversation
        state["messages"].append(AIMessage(content=response_text))
        
        return state
    
    def _handle_error_node(self, state: ConversationState) -> ConversationState:
        """Node: Handle errors"""
        error_msg = state.get("error", "An unknown error occurred")
        state["messages"].append(AIMessage(content=f"Error: {error_msg}"))
        return state
    
    # Conditional Edge Functions
    
    def _should_generate_sql(self, state: ConversationState) -> str:
        """Check if we should generate SQL"""
        if state.get("error"):
            return "error"
        return "generate"
    
    def _check_sql_valid(self, state: ConversationState) -> str:
        """Check if generated SQL is valid"""
        sql = state.get("last_sql", "")
        
        if state.get("error"):
            return "invalid"
        
        if not sql.upper().startswith("SELECT"):
            state["error"] = "Invalid SQL: doesn't start with SELECT"
            return "invalid"
        
        if "FROM" not in sql.upper():
            state["error"] = "Invalid SQL: missing FROM clause"
            return "invalid"
        
        return "valid"
    
    def _check_execution(self, state: ConversationState) -> str:
        """Check if query execution was successful"""
        if state.get("error"):
            return "error"
        return "success"
    
    # Helper Methods
    
    def _build_context(self, messages: List) -> str:
        """Build context from previous messages"""
        if not messages:
            return ""
        
        context = "Previous conversation:\n"
        for msg in messages[-6:]:
            if isinstance(msg, HumanMessage):
                context += f"User: {msg.content}\n"
            elif isinstance(msg, AIMessage):
                context += f"Assistant: {msg.content}\n"
        
        return context
    
    def _generate_session_name(self, first_message: str) -> str:
        """Generate a concise session name from the first user message"""
        # Truncate to first 40 chars and clean up
        name = first_message[:40].strip()
        # Remove question marks and periods at the end
        name = name.rstrip('?.!,')
        # If too short, add default
        if len(name) < 10:
            return "New Conversation"
        return name
    
    def save_message(self, session_id: str, role: str, content: str, 
                    sql: str = None, result_count: int = 0, success: bool = True):
        """Save message to persistent history"""
        history_conn = sqlite3.connect(self.history_db_path)
        cursor = history_conn.cursor()
        
        # Check if session exists
        cursor.execute("SELECT session_name FROM chat_sessions WHERE session_id = ?", (session_id,))
        existing = cursor.fetchone()
        
        if not existing:
            # New session - generate name from first user message
            session_name = self._generate_session_name(content) if role == 'user' else "New Chat"
            cursor.execute("""
                INSERT INTO chat_sessions (session_id, session_name) 
                VALUES (?, ?)
            """, (session_id, session_name))
        
        # Update last activity
        cursor.execute("""
            UPDATE chat_sessions 
            SET last_activity = CURRENT_TIMESTAMP 
            WHERE session_id = ?
        """, (session_id,))
        
        # Insert message
        cursor.execute("""
            INSERT INTO chat_messages 
            (session_id, role, content, sql_query, result_count, success)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_id, role, content, sql, result_count, success))
        
        history_conn.commit()
        history_conn.close()
    
    def load_session_history(self, session_id: str) -> List[Dict]:
        """Load chat history for a session"""
        history_conn = sqlite3.connect(self.history_db_path)
        
        query = """
            SELECT role, content, sql_query, result_count, success, timestamp
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY timestamp ASC
        """
        
        history_df = pd.read_sql(query, history_conn, params=(session_id,))
        history_conn.close()
        
        return history_df.to_dict('records')
    
    def get_recent_context_from_db(self, session_id: str, limit: int = 10) -> List:
        """Load recent messages from database to restore context"""
        from langchain_core.messages import HumanMessage, AIMessage
        
        history = self.load_session_history(session_id)
        messages = []
        
        # Take last N messages
        for msg in history[-limit:]:
            if msg['role'] == 'user':
                messages.append(HumanMessage(content=msg['content']))
            elif msg['role'] == 'assistant':
                messages.append(AIMessage(content=msg['content']))
        
        return messages
    
    def get_all_sessions(self) -> List[Dict]:
        """Get all chat sessions with names"""
        history_conn = sqlite3.connect(self.history_db_path)
        
        query = """
            SELECT session_id, session_name, created_at, last_activity,
                   (SELECT COUNT(*) FROM chat_messages WHERE session_id = s.session_id) as message_count
            FROM chat_sessions s
            ORDER BY last_activity DESC
        """
        
        sessions_df = pd.read_sql(query, history_conn)
        history_conn.close()
        
        return sessions_df.to_dict('records')
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages"""
        try:
            history_conn = sqlite3.connect(self.history_db_path)
            cursor = history_conn.cursor()
            
            # Delete all messages in the session
            cursor.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            
            # Delete the session itself
            cursor.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))
            
            history_conn.commit()
            history_conn.close()
            return True
        except Exception as e:
            print(f"Error deleting session: {e}")
            return False
    
    def process_message(self, user_message: str, session_id: str, 
                       existing_messages: List = None) -> QueryResult:
        """Process a user message through the LangGraph workflow"""
        
        # Initialize state - use existing messages or load from database
        if existing_messages:
            messages = existing_messages.copy()
        else:
            # Load recent context from database for better memory
            messages = self.get_recent_context_from_db(session_id, limit=10)
        
        messages.append(HumanMessage(content=user_message))
        
        initial_state = ConversationState(
            messages=messages,
            database_path=self.db_path,
            database_schema=self.schema,
            last_sql="",
            last_result=None,
            session_id=session_id,
            query_count=0,
            error=""
        )
        
        # Run the graph
        final_state = self.graph.invoke(initial_state)
        
        # Extract results
        success = not bool(final_state.get("error"))
        sql = final_state.get("last_sql", "")
        data = final_state.get("last_result")
        error = final_state.get("error", "")
        
        # Save to history
        self.save_message(
            session_id=session_id,
            role="user",
            content=user_message,
            success=True
        )
        
        if success and data is not None:
            result_count = len(data)
            self.save_message(
                session_id=session_id,
                role="assistant",
                content=final_state["messages"][-1].content,
                sql=sql,
                result_count=result_count,
                success=True
            )
        else:
            self.save_message(
                session_id=session_id,
                role="assistant",
                content=error,
                sql=sql,
                result_count=0,
                success=False
            )
        
        # Return result
        return QueryResult(
            question=user_message,
            sql=sql,
            data=data if data is not None else pd.DataFrame(),
            success=success,
            error=error if not success else None,
            timestamp=datetime.now().isoformat()
        )
    
    def close(self):
        """Close database connections"""
        if self.conn:
            self.conn.close()
