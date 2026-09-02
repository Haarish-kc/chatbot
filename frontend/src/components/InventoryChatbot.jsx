import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import '../index.css';

// Configure the backend URL based on environment
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const BACKEND_URL = `${API_BASE_URL}/api/chat`;

const getStoredToken = () => {
  let token = localStorage.getItem("access_token") || 
              localStorage.getItem("token") || 
              localStorage.getItem("accessToken") || 
              localStorage.getItem("jwt") ||
              localStorage.getItem("auth_token") || 
              sessionStorage.getItem("access_token") || 
              sessionStorage.getItem("token") || 
              sessionStorage.getItem("accessToken") || 
              sessionStorage.getItem("jwt") || 
              null;
  if (token) {
    token = token.replace(/^"|"$/g, '').trim();
    if (token.startsWith('Bearer ')) token = token.slice(7).trim();
  }
  return token;
};

function InventoryChatbot() {
  const initialGreeting = "Hey! 👋 I'm your Inventory AI Assistant. How can I assist you?\n\nYou can use these tags to reference items:\n\n• **@** — People  \n• **PNR@** — Purchase Requests  \n• **INV@** — Invoices  \n• **PO@** — Purchase Orders  \n• **AST@** — Assets";
  
  const [isOpen, setIsOpen] = useState(true);
  const [messages, setMessages] = useState([
    {
      id: 1,
      sender: 'bot',
      text: initialGreeting,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      isError: false
    }
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  
  // UI Enhancements State
  const [isHelpMenuOpen, setIsHelpMenuOpen] = useState(false);
  const [activePanel, setActivePanel] = useState(null); // null | 'feedback' | 'assistance' | 'mail'
  const [supportDesc, setSupportDesc] = useState('');
  const [supportIssueType, setSupportIssueType] = useState('Technical Issue');
  const [supportAttachment, setSupportAttachment] = useState(null); // {filename, content}
  const [isSubmittingSupport, setIsSubmittingSupport] = useState(false);
  const [feedbackText, setFeedbackText] = useState('');
  const [feedbackRating, setFeedbackRating] = useState(0);
  
  // Gen Z UI States
  const [unreadCount, setUnreadCount] = useState(0);
  const [showSearch, setShowSearch] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [feedback, setFeedback] = useState({}); // { msgId: 'up' | 'down' }
  const [userRole, setUserRole] = useState('');
  const [userDept, setUserDept] = useState('');
  const [userName, setUserName] = useState('');
  const [isLoadingProfile, setIsLoadingProfile] = useState(true);
  const [isSystemOffline, setIsSystemOffline] = useState(false);

  useEffect(() => {
    let isMounted = true;
    const token = getStoredToken();
    
    const headers = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    // Fetch full profile from /api/me for the real profile info
    fetch(`${API_BASE_URL}/api/me`, { headers })
        .then(r => {
          if (!r.ok) {
            console.error("Profile fetch response not OK:", r.status, r.statusText);
            return null;
          }
          return r.json();
        })
        .then(data => {
          if (isMounted) {
            setIsLoadingProfile(false);
            if (data) {
              const firstName = data.firstName || data.name?.split(' ')[0] || '';
              setUserName(firstName);
              if (data.role) setUserRole(data.role.toUpperCase());
              if (data.department) setUserDept(data.department);

              // Patch the initial greeting message to include the user's name
              if (firstName) {
                setMessages(prev => prev.map((msg, idx) =>
                  idx === 0 && msg.sender === 'bot'
                    ? { ...msg, text: `Hey, ${firstName}! 👋\nI'm your Inventory AI Assistant. How can I assist you?\n\nYou can use these tags to reference items:\n\n• **@** — People  \n• **PNR@** — Purchase Requests  \n• **INV@** — Invoices  \n• **PO@** — Purchase Orders  \n• **AST@** — Assets` }
                    : msg
                ));
              }
            }
          }
        })
        .catch(err => {
          console.error("Profile fetch failed error:", err);
          if (isMounted) setIsLoadingProfile(false);
        });

    // Check backend AI / Quota status
    fetch(`${API_BASE_URL}/api/status`)
        .then(r => r.ok ? r.json() : null)
        .then(statusData => {
          if (isMounted && statusData) {
            setIsSystemOffline(Boolean(statusData.is_offline));
          }
        })
        .catch(err => {
          console.error("Status check error:", err);
        });

    return () => { isMounted = false; };
  }, []);
  
  // Autocomplete State
  const [entityType, setEntityType] = useState(null); // 'user' | 'pr' | 'inv' | 'po'
  const [entityOptions, setEntityOptions] = useState([]);
  const [showAutocomplete, setShowAutocomplete] = useState(false);
  const [autocompleteSearch, setAutocompleteSearch] = useState('');
  const [selectedIdx, setSelectedIdx] = useState(0);

  // Track tagged entities/mentions metadata
  const [taggedMentions, setTaggedMentions] = useState([]); // {user_id, username}
  const [taggedEntities, setTaggedEntities] = useState([]); // {type, id, reference}

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const chatMessagesRef = useRef(null);
  const helpMenuRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (helpMenuRef.current && !helpMenuRef.current.contains(event.target)) {
        setIsHelpMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
      inputRef.current?.focus();
    }
  }, [messages, isLoading, isOpen, activePanel]);

  useEffect(() => {
    if (!chatMessagesRef.current) return;
    
    // Auto-scroll globally whenever anything inside the messages container changes
    const observer = new MutationObserver(() => {
      scrollToBottom();
    });
    
    observer.observe(chatMessagesRef.current, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true
    });
    
    return () => {
      observer.disconnect();
    };
  }, [isOpen]);

  const fetchEntities = async (type) => {
    try {
      const userToken = getStoredToken();
      const headers = {};
      if (userToken) {
        headers['Authorization'] = `Bearer ${userToken}`;
      }
      
      let url = '';
      if (type === 'user') {
        const prMatch = inputValue.match(/PR@([a-zA-Z0-9_-]+)/i);
        const prParam = prMatch ? `?pr_number=${prMatch[1]}` : '';
        url = `${API_BASE_URL}/api/mentions/allowed${prParam}`;
      }
      else if (type === 'pr') url = `${API_BASE_URL}/api/entities/purchase-requests`;
      else if (type === 'inv') url = `${API_BASE_URL}/api/entities/invoices`;
      else if (type === 'po') url = `${API_BASE_URL}/api/entities/purchase-orders`;
      else if (type === 'asset') url = `${API_BASE_URL}/api/entities/assets`;
      
      const res = await fetch(url, { headers });
      if (res.ok) {
        const data = await res.json();
        setEntityOptions(data);
      }
    } catch (error) {
      console.error(`Error fetching entities of type ${type}:`, error);
    }
  };

  const filteredOptions = entityOptions.filter(opt => {
    if (!opt) return false;
    const search = (autocompleteSearch || '').toLowerCase();
    if (entityType === 'user') {
      const username = (opt.username || '').toLowerCase();
      const name = (opt.name || '').toLowerCase();
      return username.includes(search) || name.includes(search);
    }
    // For PR/PO/Invoice
    const ref = (opt.reference || '').toLowerCase();
    const desc = (opt.description || '').toLowerCase();
    const supplier = (opt.supplier || '').toLowerCase();
    return ref.includes(search) || desc.includes(search) || supplier.includes(search);
  });

  const handleInputChange = async (e) => {
    const val = e.target.value;
    setInputValue(val);
    
    const cursorPosition = e.target.selectionStart;
    const textBeforeCursor = val.slice(0, cursorPosition);
    
    // Check PR@ / PNR@
    let pnrIndex = textBeforeCursor.lastIndexOf('PR@');
    let prefixLen = 3;
    if (pnrIndex === -1) {
      pnrIndex = textBeforeCursor.lastIndexOf('PNR@');
      prefixLen = 4;
    }
    if (pnrIndex !== -1 && (pnrIndex === 0 || textBeforeCursor[pnrIndex - 1] === ' ' || textBeforeCursor[pnrIndex - 1] === '\n')) {
      const query = textBeforeCursor.slice(pnrIndex + prefixLen);
      if (!query.includes(' ')) {
        setEntityType('pr');
        setAutocompleteSearch(query);
        setShowAutocomplete(true);
        setSelectedIdx(0);
        await fetchEntities('pr');
        return;
      }
    }
    
    // Check INV@
    const invIndex = textBeforeCursor.lastIndexOf('INV@');
    if (invIndex !== -1 && (invIndex === 0 || textBeforeCursor[invIndex - 1] === ' ' || textBeforeCursor[invIndex - 1] === '\n')) {
      const query = textBeforeCursor.slice(invIndex + 4);
      if (!query.includes(' ')) {
        setEntityType('inv');
        setAutocompleteSearch(query);
        setShowAutocomplete(true);
        setSelectedIdx(0);
        await fetchEntities('inv');
        return;
      }
    }
    
    // Check PO@
    const poIndex = textBeforeCursor.lastIndexOf('PO@');
    if (poIndex !== -1 && (poIndex === 0 || textBeforeCursor[poIndex - 1] === ' ' || textBeforeCursor[poIndex - 1] === '\n')) {
      const query = textBeforeCursor.slice(poIndex + 3);
      if (!query.includes(' ')) {
        setEntityType('po');
        setAutocompleteSearch(query);
        setShowAutocomplete(true);
        setSelectedIdx(0);
        await fetchEntities('po');
        return;
      }
    }
    
    // Check AST@
    const astIndex = textBeforeCursor.lastIndexOf('AST@');
    if (astIndex !== -1 && (astIndex === 0 || textBeforeCursor[astIndex - 1] === ' ' || textBeforeCursor[astIndex - 1] === '\n')) {
      const query = textBeforeCursor.slice(astIndex + 4);
      if (!query.includes(' ')) {
        setEntityType('asset');
        setAutocompleteSearch(query);
        setShowAutocomplete(true);
        setSelectedIdx(0);
        await fetchEntities('asset');
        return;
      }
    }
    
    // Check @ (User/Manager)
    const atIndex = textBeforeCursor.lastIndexOf('@');
    if (atIndex !== -1 && (atIndex === 0 || textBeforeCursor[atIndex - 1] === ' ' || textBeforeCursor[atIndex - 1] === '\n')) {
      const hasPrefix = (atIndex >= 2 && textBeforeCursor.slice(atIndex - 2, atIndex) === 'PR') ||
                        (atIndex >= 3 && textBeforeCursor.slice(atIndex - 3, atIndex) === 'INV') ||
                        (atIndex >= 2 && textBeforeCursor.slice(atIndex - 2, atIndex) === 'PO') ||
                        (atIndex >= 3 && textBeforeCursor.slice(atIndex - 3, atIndex) === 'AST');
      if (!hasPrefix) {
        const query = textBeforeCursor.slice(atIndex + 1);
        if (!query.includes(' ')) {
          setEntityType('user');
          setAutocompleteSearch(query);
          setShowAutocomplete(true);
          setSelectedIdx(0);
          await fetchEntities('user');
          return;
        }
      }
    }
    
    setShowAutocomplete(false);
  };

  const selectOption = (opt) => {
    if (!opt) return;
    
    const cursorPosition = inputRef.current ? inputRef.current.selectionStart : 0;
    const textBeforeCursor = inputValue.slice(0, cursorPosition);
    const textAfterCursor = inputValue.slice(cursorPosition);
    
    let newTextBeforeCursor = '';
    
    if (entityType === 'pr' && opt.reference) {
      let lastIndex = textBeforeCursor.lastIndexOf('PR@');
      let prefix = 'PR@';
      if (lastIndex === -1) {
        lastIndex = textBeforeCursor.lastIndexOf('PNR@');
        prefix = 'PNR@';
      }
      if (lastIndex !== -1) {
        newTextBeforeCursor = textBeforeCursor.slice(0, lastIndex) + `${prefix}${opt.reference} `;
      } else {
        newTextBeforeCursor = textBeforeCursor + `PR@${opt.reference} `;
      }
      setTaggedEntities(prev => [...prev, {
        type: 'purchase_request',
        id: opt.id,
        reference: opt.reference
      }]);
    }
    else if (entityType === 'inv' && opt.reference) {
      const lastIndex = textBeforeCursor.lastIndexOf('INV@');
      if (lastIndex !== -1) {
        newTextBeforeCursor = textBeforeCursor.slice(0, lastIndex) + `INV@${opt.reference} `;
      } else {
        newTextBeforeCursor = textBeforeCursor + `INV@${opt.reference} `;
      }
      setTaggedEntities(prev => [...prev, {
        type: 'invoice',
        id: opt.id,
        reference: opt.reference
      }]);
    }
    else if (entityType === 'po' && opt.reference) {
      const lastIndex = textBeforeCursor.lastIndexOf('PO@');
      if (lastIndex !== -1) {
        newTextBeforeCursor = textBeforeCursor.slice(0, lastIndex) + `PO@${opt.reference} `;
      } else {
        newTextBeforeCursor = textBeforeCursor + `PO@${opt.reference} `;
      }
      setTaggedEntities(prev => [...prev, {
        type: 'purchase_order',
        id: opt.id,
        reference: opt.reference
      }]);
    }
    else if (entityType === 'asset' && opt.reference) {
      const lastIndex = textBeforeCursor.lastIndexOf('AST@');
      if (lastIndex !== -1) {
        newTextBeforeCursor = textBeforeCursor.slice(0, lastIndex) + `AST@${opt.reference} `;
      } else {
        newTextBeforeCursor = textBeforeCursor + `AST@${opt.reference} `;
      }
      setTaggedEntities(prev => [...prev, {
        type: 'asset',
        id: opt.id,
        reference: opt.reference
      }]);
    }
    else if (entityType === 'user') {
      const mentionTag = opt.username || opt.name?.split(' ')[0]?.toLowerCase() || `user_${opt.id}`;
      const lastIndex = textBeforeCursor.lastIndexOf('@');
      if (lastIndex !== -1) {
        newTextBeforeCursor = textBeforeCursor.slice(0, lastIndex) + `@${mentionTag} `;
      } else {
        newTextBeforeCursor = textBeforeCursor + `@${mentionTag} `;
      }
      setTaggedMentions(prev => [...prev, {
        user_id: opt.id,
        username: mentionTag
      }]);
    } else {
      newTextBeforeCursor = textBeforeCursor;
    }
    
    setInputValue(newTextBeforeCursor + textAfterCursor);
    setShowAutocomplete(false);
    
    // Focus back & position cursor
    setTimeout(() => {
      if (inputRef.current) {
        inputRef.current.focus();
        const newCursorPos = newTextBeforeCursor.length;
        inputRef.current.setSelectionRange(newCursorPos, newCursorPos);
      }
    }, 50);
  };

  const handleSupportSubmit = async (e) => {
    e.preventDefault();
    if (!supportDesc.trim()) return;
    
    setIsSubmittingSupport(true);
    try {
      let userToken = localStorage.getItem("access_token") || sessionStorage.getItem("access_token") || localStorage.getItem("token");
      const headers = {
        'Content-Type': 'application/json'
      };
      if (userToken) {
        userToken = userToken.replace(/^"|"$/g, '').trim();
        if (userToken.startsWith('Bearer ')) userToken = userToken.slice(7).trim();
        headers['Authorization'] = `Bearer ${userToken}`;
      }
      
      const payload = {
        description: supportDesc,
        issue_type: supportIssueType,
        attachment: supportAttachment
      };
      
      const res = await fetch(`${API_BASE_URL}/api/support`, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload)
      });
      
      if (res.ok) {
        setMessages(prev => [
          ...prev,
          {
            id: Date.now(),
            sender: 'bot',
            text: "✅ Your issue has been sent successfully via mail.",
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            isError: false
          }
        ]);
        setSupportDesc('');
        setSupportAttachment(null);
        setActivePanel(null);
      } else {
        const errData = await res.json();
        setMessages(prev => [
          ...prev,
          {
            id: Date.now(),
            sender: 'bot',
            text: errData.detail || "⚠️ We couldn't send your issue right now. Please try again later.",
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            isError: true
          }
        ]);
        setActivePanel(null);
      }
    } catch (err) {
      console.error("Error submitting support request:", err);
      setMessages(prev => [
        ...prev,
        {
          id: Date.now(),
          sender: 'bot',
          text: "⚠️ We couldn't send your issue right now. Please try again later.",
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          isError: true
        }
      ]);
      setActivePanel(null);
    } finally {
      setIsLoading(false);
      setIsSubmittingSupport(false);
    }
  };

  const handleWhatsAppRedirect = () => {
    const whatsappNum = import.meta.env.VITE_WHATSAPP_SUPPORT_NUMBER || '919000000000';
    let message = 'Hello, I need help with an issue in the Inventory AI Assistant.';
    if (userName) {
      message = `Hello, I need help with an issue in the Inventory AI Assistant.\n\nUser: ${userName}\nDepartment: ${userDept || 'General'}\n\nIssue:\n`;
    }
    const encodedMessage = encodeURIComponent(message);
    const url = `https://wa.me/${whatsappNum}?text=${encodedMessage}`;
    window.open(url, '_blank');
  };

  const handleSupportFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    
    const reader = new FileReader();
    reader.onloadend = () => {
      setSupportAttachment({
        filename: file.name,
        content: reader.result
      });
    };
    reader.readAsDataURL(file);
  };

  const handleSend = async (text) => {
    const trimmedText = text.trim();
    if (!trimmedText) return;

    // Add user message
    const userMsg = {
      id: Date.now(),
      sender: 'user',
      text: trimmedText,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      isError: false
    };
    setMessages(prev => [...prev, userMsg]);
    setInputValue('');
    setShowAutocomplete(false);
    setIsLoading(true);

    try {
      const userToken = getStoredToken();
      const headers = {
        'Content-Type': 'application/json',
      };
      if (userToken) {
        headers['Authorization'] = `Bearer ${userToken}`;
      }

      // Filter structured mentions/entities to verify they are still present in text
      const finalMentions = taggedMentions.filter(m => 
        trimmedText.toLowerCase().includes(`@${m.username.toLowerCase()}`)
      );
      
      const finalEntities = taggedEntities.filter(e => 
        (e.type === 'purchase_request' && trimmedText.toLowerCase().includes(`pr@${e.reference.toLowerCase()}`)) ||
        (e.type === 'invoice' && trimmedText.toLowerCase().includes(`inv@${e.reference.toLowerCase()}`)) ||
        (e.type === 'purchase_order' && trimmedText.toLowerCase().includes(`po@${e.reference.toLowerCase()}`)) ||
        (e.type === 'asset' && trimmedText.toLowerCase().includes(`ast@${e.reference.toLowerCase()}`))
      );

      const response = await fetch(BACKEND_URL, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ 
          message: trimmedText,
          mentions: finalMentions.length > 0 ? finalMentions : null,
          entities: finalEntities.length > 0 ? finalEntities : null
        }),
      });

      if (!response.ok) {
        if (response.status === 429) {
          setIsSystemOffline(true);
        }
        try {
          const errData = await response.json();
          throw new Error(errData.detail || 'Network response was not ok');
        } catch (jsonErr) {
          throw new Error('Network response was not ok');
        }
      }

      const data = await response.json();
      if (data && typeof data.is_offline !== 'undefined') {
        setIsSystemOffline(Boolean(data.is_offline));
      } else {
        setIsSystemOffline(false);
      }
      
      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        sender: 'bot',
        text: data.response,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        isError: false
      }]);
      
      if (!isOpen) {
        setUnreadCount(prev => prev + 1);
      }
      
      setTaggedMentions([]);
      setTaggedEntities([]);
    } catch (error) {
      console.error('Error fetching chat response:', error);
      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        sender: 'bot',
        text: error.message || "I'm unable to connect to the server right now. Please try again later.",
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        isError: true
      }]);
      if (!isOpen) {
        setUnreadCount(prev => prev + 1);
      }
    } finally {
      setIsLoading(false);
      if (inputRef.current) {
        inputRef.current.focus();
      }
    }
  };

  const handleKeyDown = (e) => {
    if (showAutocomplete && filteredOptions.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIdx(prev => (prev + 1) % filteredOptions.length);
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIdx(prev => (prev - 1 + filteredOptions.length) % filteredOptions.length);
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        selectOption(filteredOptions[selectedIdx]);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setShowAutocomplete(false);
        return;
      }
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend(inputValue);
    }
  };

  const clearChat = () => {
    setMessages([
      {
        id: Date.now(),
        sender: 'bot',
        text: "Chat cleared. How can I help you today?",
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        isError: false
      }
    ]);
    setTaggedMentions([]);
    setTaggedEntities([]);
    setShowAutocomplete(false);
  };

  const handleFeedback = (msgId, type) => {
    setFeedback(prev => ({
      ...prev,
      [msgId]: prev[msgId] === type ? null : type
    }));
  };

  // Dynamic contextual suggestions based on bot message content
  const getSuggestions = (text) => {
    const t = text.toLowerCase();
    if (t.includes('purchase request') || t.includes('pr') || t.includes('pr@')) {
      return ["Show pending purchase requests", "Show approved purchase requests", "Show my latest purchase request"];
    }
    if (t.includes('asset') || t.includes('ast@')) {
      return ["Show assigned assets", "Show my latest assets", "Show asset details"];
    }
    if (t.includes('expense')) {
      return ["Show pending expenses", "Show recent expenses"];
    }
    if (t.includes('location') || t.includes('station')) {
      return ["Show Chennai locations", "Show station locations"];
    }
    return [];
  };

  // Filters messages based on Search overlay
  const filteredMessages = searchQuery
    ? messages.filter(msg => msg.text.toLowerCase().includes(searchQuery.toLowerCase()))
    : messages;

  return (
    <div className="floating-chatbot-wrapper">
      <button 
        className={`chatbot-launcher ${isOpen ? 'hidden' : ''}`}
        onClick={() => {
          setIsOpen(true);
          setUnreadCount(0);
        }}
        aria-label="Open AI Assistant"
      >
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path>
        </svg>
        {unreadCount > 0 && <span className="unread-badge">{unreadCount}</span>}
      </button>

      <div className={`chatbot-container ${isOpen ? 'open' : 'closed'}`}>
        <div className="chatbot-header">
          <div className="chatbot-title">
            <div className="header-avatar-square">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2v4M8 5h8" />
                <rect x="3" y="11" width="18" height="10" rx="2" />
                <circle cx="8" cy="16" r="1.5" fill="currentColor" />
                <circle cx="16" cy="16" r="1.5" fill="currentColor" />
              </svg>
            </div>
            <div className="chatbot-title-text">
              <h1>AI Assistant</h1>
              <span className="chatbot-status">
                {isLoadingProfile ? (
                  <>
                    <span className="status-role">Loading...</span>
                    <span className="status-sep">|</span>
                  </>
                ) : (
                  <>
                    {userName && <span className="status-name" style={{ fontWeight: 600, fontSize: '12px', color: 'rgba(255,255,255,0.7)' }}>{userName}</span>}
                    {userName && userRole && <span className="status-sep">|</span>}
                    {userRole && <span className="status-role">{userRole}</span>}
                    {(userName || userRole) && <span className="status-sep">|</span>}
                  </>
                )}
                <span className={`status-dot ${isSystemOffline ? 'offline' : ''}`} />
                <span className="status-online-text">{isSystemOffline ? 'OFFLINE' : 'ONLINE'}</span>
              </span>
            </div>
          </div>
          <div className="header-actions">
            <div className="help-menu-wrapper" ref={helpMenuRef} style={{ position: 'relative' }}>
              <button 
                className="help-pill-btn"
                onClick={() => setIsHelpMenuOpen(!isHelpMenuOpen)} 
                title="Help & Support"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10"></circle>
                  <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path>
                  <line x1="12" y1="17" x2="12.01" y2="17"></line>
                </svg>
                Help
              </button>
              
              {isHelpMenuOpen && (
                <div className="help-dropdown-menu">
                  <button onClick={() => {
                    setIsHelpMenuOpen(false);
                    setActivePanel('feedback');
                  }}>
                    💬 Feedback
                  </button>
                  <button onClick={() => {
                    setIsHelpMenuOpen(false);
                    setActivePanel('assistance');
                    setTimeout(scrollToBottom, 50);
                  }}>
                    🛠 Need Assistance
                  </button>
                </div>
              )}
            </div>

            <button className="icon-btn chevron-btn" onClick={() => { setIsOpen(false); setShowSearch(false); setSearchQuery(''); }} title="Minimize">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="6 9 12 15 18 9"></polyline>
              </svg>
            </button>
          </div>
        </div>

        {showSearch && (
          <div className="search-overlay">
            <input 
              type="text" 
              placeholder="Search in this chat..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="search-input"
              autoFocus
            />
            <button className="search-close" onClick={() => { setShowSearch(false); setSearchQuery(''); }} title="Close search">
              ✕
            </button>
          </div>
        )}

        <div className="chat-messages" ref={chatMessagesRef}>
          {filteredMessages.map((msg, idx) => (
            <React.Fragment key={msg.id}>
              <div className={`message-wrapper ${msg.sender} ${msg.isError ? 'error' : ''}`}>
                {msg.sender === 'bot' && (
                  <div className="avatar bot ai-label-avatar">AI</div>
                )}
                {msg.sender === 'user' && <div className="avatar user">👤</div>}
                
                <div className="message-container-with-meta">
                  <div className="message-content">
                    {msg.sender === 'bot' ? (
                      <div className="bot-markdown">
                        <ReactMarkdown
                          components={{
                            a: ({ node, children, href, ...props }) => {
                              return (
                                <a
                                  {...props}
                                  href={href}
                                  onClick={(e) => {
                                    if (href && (href.startsWith('http://') || href.startsWith('https://') || href.startsWith('/'))) {
                                      e.preventDefault();
                                      window.open(href, '_blank', 'noopener,noreferrer');
                                      return;
                                    }
                                    e.preventDefault();
                                    const textContent = React.Children.toArray(children).join('').trim();
                                    if (textContent) {
                                      handleSend(textContent);
                                    } else if (href) {
                                      handleSend(href);
                                    }
                                  }}
                                  style={{ cursor: 'pointer', color: '#2563eb', textDecoration: 'underline', fontWeight: 600 }}
                                >
                                  {children}
                                </a>
                              );
                            }
                          }}
                        >
                          {msg.text}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      msg.text
                    )}
                  </div>
                  {msg.timestamp && <span className="message-timestamp">{msg.timestamp}</span>}
                  

                </div>
              </div>

              {/* Suggestions chips underneath final bot response */}
              {msg.sender === 'bot' && idx === filteredMessages.length - 1 && idx !== 0 && !isLoading && (
                (() => {
                  const lastUserText = [...messages].reverse().find(m => m.sender === 'user')?.text || '';
                  const finalSuggestions = getSuggestions(msg.text).filter(sug => 
                    sug.toLowerCase().trim() !== lastUserText.toLowerCase().trim()
                  );
                  if (finalSuggestions.length === 0) return null;
                  return (
                    <div className="suggestion-chips-container">
                      {finalSuggestions.map((sug, sIdx) => (
                        <button 
                          key={`sug-${sIdx}`} 
                          className="suggestion-chip" 
                          onClick={() => handleSend(sug)}
                        >
                          {sug}
                        </button>
                      ))}
                    </div>
                  );
                })()
              )}
            </React.Fragment>
          ))}
          
          {isLoading && (
            <div className="message-wrapper bot">
              <div className="avatar bot ai-label-avatar">AI</div>
              <div className="thinking-text" style={{ padding: '10px 14px' }}>
                <span className="thinking-dots">
                  <span className="thinking-dot"></span>
                  <span className="thinking-dot"></span>
                  <span className="thinking-dot"></span>
                </span>
              </div>
            </div>
          )}
          {messages.length === 1 && (
            <div className="quick-actions-grid">
              <button className="quick-action-btn" onClick={() => handleSend("How to use the assistant")}>
                💡 Hints
              </button>
              <button className="quick-action-btn" onClick={() => handleSend("Show my purchase requests")}>
                📄 My PRs
              </button>
              <button className="quick-action-btn" onClick={() => { setActivePanel('assets_selection'); setTimeout(scrollToBottom, 50); }}>
                💼 My Assets
              </button>
              <button className="quick-action-btn" onClick={() => handleSend("Show my expenses")}>
                💰 My Expenses
              </button>
            </div>
          )}

          {activePanel === 'assets_selection' && (
            <div className="support-form-card">
              <h3>💼 My Assets</h3>
              <div className="form-group" style={{ marginBottom: '16px' }}>
                <label>Which assets would you like to view?</label>
              </div>
              <div className="form-actions" style={{ flexDirection: 'column', gap: '8px' }}>
                <button 
                  type="button" 
                  onClick={() => {
                    setActivePanel(null);
                    handleSend("Show station assets");
                  }}
                  style={{ width: '100%', justifyContent: 'center' }}
                >
                  🚉 Station Assets
                </button>
                <button 
                  type="button" 
                  onClick={() => {
                    setActivePanel(null);
                    handleSend("Show employee assets");
                  }}
                  style={{ width: '100%', justifyContent: 'center' }}
                >
                  👤 Employee Assets
                </button>
                <button 
                  type="button" 
                  onClick={() => setActivePanel(null)}
                  style={{ width: '100%', justifyContent: 'center', backgroundColor: '#f1f5f9', color: '#64748b', border: '1px solid #cbd5e1' }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {activePanel === 'assistance' && (
            <div className="support-form-card">
              <h3>🛠 Need Assistance</h3>
              <div className="form-group" style={{ marginBottom: '16px' }}>
                <label>How would you like to get help?</label>
              </div>
              <div className="form-actions" style={{ flexDirection: 'column', gap: '8px' }}>
                <button 
                  type="button" 
                  onClick={() => {
                    setSupportIssueType("Via Mail");
                    setActivePanel('mail');
                    setTimeout(scrollToBottom, 50);
                  }}
                  style={{ width: '100%', justifyContent: 'center' }}
                >
                  📧 Via Mail
                </button>
                <button 
                  type="button" 
                  onClick={() => {
                    setActivePanel(null);
                    handleWhatsAppRedirect();
                  }}
                  style={{ width: '100%', justifyContent: 'center', backgroundColor: '#25d366', color: 'white', border: 'none' }}
                >
                  💬 Via WhatsApp
                </button>
                <button 
                  type="button" 
                  onClick={() => setActivePanel(null)}
                  style={{ width: '100%', justifyContent: 'center', backgroundColor: '#f1f5f9', color: '#64748b', border: '1px solid #cbd5e1' }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {activePanel === 'mail' && (
            <div className="support-form-card">
              <h3>📝 Need Assistance</h3>
              <form onSubmit={handleSupportSubmit}>
                <div className="form-group">
                  <label>Issue Description</label>
                  <textarea 
                    placeholder="Describe the issue..." 
                    value={supportDesc}
                    onChange={(e) => setSupportDesc(e.target.value)}
                    required
                  />
                </div>
                <div className="form-group">
                  <label>Attachment (Optional)</label>
                  <input 
                    type="file" 
                    onChange={handleSupportFileChange}
                    accept="image/*,application/pdf"
                  />
                  {supportAttachment && (
                    <span className="file-info">📎 {supportAttachment.filename}</span>
                  )}
                </div>
                <div className="form-actions">
                  <button type="submit" disabled={isSubmittingSupport}>
                    {isSubmittingSupport ? "Sending..." : "Send"}
                  </button>
                  <button type="button" onClick={() => {
                    setActivePanel(null);
                    setSupportDesc('');
                    setSupportAttachment(null);
                  }}>
                    Cancel
                  </button>
                </div>
              </form>
            </div>
          )}

          {activePanel === 'feedback' && (
            <div className="support-form-card feedback-form-card">
              <h3>💬 Share Your Feedback</h3>
              <div className="form-group">
                <label>How was your experience?</label>
                <div className="feedback-stars">
                  {[1, 2, 3, 4, 5].map(star => (
                    <button
                      key={star}
                      type="button"
                      className={`star-btn ${feedbackRating >= star ? 'active' : ''}`}
                      onClick={() => setFeedbackRating(star)}
                      aria-label={`Rate ${star} star`}
                    >
                      ★
                    </button>
                  ))}
                </div>
              </div>
              <div className="form-group">
                <label>Tell us more (optional)</label>
                <textarea
                  placeholder="Your feedback..."
                  value={feedbackText}
                  onChange={(e) => setFeedbackText(e.target.value)}
                />
              </div>
              <div className="form-actions">
                <button
                  type="button"
                  onClick={() => {
                    const rating = feedbackRating ? `${feedbackRating}/5 ⭐` : '';
                    const msg = [
                      rating && `Rating: ${rating}`,
                      feedbackText && `Feedback: "${feedbackText}"`
                    ].filter(Boolean).join(' — ');
                    setMessages(prev => [...prev, {
                      id: Date.now(),
                      sender: 'bot',
                      text: `✅ Thank you for your feedback!${msg ? ' ' + msg : ''} We appreciate you helping us improve.`,
                      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                      isError: false
                    }]);
                    setActivePanel(null);
                    setFeedbackText('');
                    setFeedbackRating(0);
                  }}
                >
                  Submit
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setActivePanel(null);
                    setFeedbackText('');
                    setFeedbackRating(0);
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {showAutocomplete && filteredOptions.length > 0 && (
          <div className="mentions-dropdown">
            <div className="autocomplete-header">
              {entityType === 'user' && (inputValue.match(/PR@([a-zA-Z0-9_-]+)/i) ? '👥 People you can tag for this request' : '👤 People')}
              {entityType === 'pr' && '🛒 Purchase Requests'}
              {entityType === 'inv' && '📄 Invoices'}
              {entityType === 'po' && '📦 Purchase Orders'}
              {entityType === 'asset' && '🏷️ Assets'}
            </div>
            {filteredOptions.map((opt, idx) => (
              <div 
                key={`${entityType}-${opt.id || opt.reference || idx}`} 
                className={`mention-item ${idx === selectedIdx ? 'active' : ''}`}
                onClick={() => selectOption(opt)}
              >
                {entityType === 'user' ? (
                  <>
                    <div className="mention-avatar">
                      {opt.name ? opt.name.charAt(0).toUpperCase() : '?'}
                    </div>
                    <div className="mention-details">
                      <span className="mention-username">@{opt.username || opt.name?.split(' ')[0]?.toLowerCase() || opt.name}</span>
                      <span className="mention-name">
                        {opt.name}
                        {opt.department ? ` · ${opt.department}` : ''}
                        {opt.role ? ` · ${opt.role}` : ''}
                      </span>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="entity-icon">
                      {entityType === 'pr' && '🛒'}
                      {entityType === 'inv' && '📄'}
                      {entityType === 'po' && '📦'}
                      {entityType === 'asset' && '🏷️'}
                    </div>
                    <div className="mention-details">
                      <span className="mention-username">
                        {entityType === 'pr' && `PR@${opt.reference}`}
                        {entityType === 'inv' && `INV@${opt.reference}`}
                        {entityType === 'po' && `PO@${opt.reference}`}
                        {entityType === 'asset' && `AST@${opt.reference}`}
                      </span>
                      <span className="mention-name">
                        {opt.description || opt.supplier || ''} 
                        {opt.status ? ` · ${opt.status}` : ''}
                        {opt.amount ? ` · ₹${opt.amount}` : ''}
                        {opt.location ? ` · ${opt.location}` : ''}
                      </span>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        )}

        <div className="input-area">
          <input
            type="text"
            ref={inputRef}
            className="chat-input"
            placeholder="Ask a question or type @ to mention..."
            value={inputValue}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
          />
          <button 
            className="send-btn" 
            onClick={() => handleSend(inputValue)}
            disabled={!inputValue.trim() || isLoading}
            aria-label="Send message"
          >
            <svg viewBox="0 0 24 24">
              <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
            </svg>
          </button>
        </div>

      </div>
    </div>
  );
}

export default InventoryChatbot;
