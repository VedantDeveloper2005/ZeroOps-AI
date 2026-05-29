"use client";

import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Brain, X, Send, Sparkles, Loader2, MessageSquare, Terminal, HelpCircle } from "lucide-react";
import { api } from "@/lib/api";
import { useNotifications } from "@/lib/NotificationContext";

interface Message {
  id: string;
  sender: "user" | "ai";
  text: string;
  timestamp: Date;
}

export function FloatingAssistant() {
  const { projects, addToast } = useNotifications();
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      sender: "ai",
      text: "Hi! I am your ZeroOps AI DevOps Assistant. Ask me anything about your deployments, logs, architecture, or configuration.",
      timestamp: new Date(),
    },
  ]);
  const [inputValue, setInputValue] = useState("");
  const [loading, setLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const activeProject = projects[0];
  const projectId = activeProject?.id;

  // Auto scroll to bottom on new messages
  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, loading]);

  const handleSendMessage = async (textToSend: string) => {
    if (!textToSend.trim() || loading) return;

    const userMessage: Message = {
      id: Math.random().toString(),
      sender: "user",
      text: textToSend,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue("");
    setLoading(true);

    try {
      const res = await api.sendChatRequest(textToSend, projectId);
      
      const aiMessage: Message = {
        id: Math.random().toString(),
        sender: "ai",
        text: res.reply || "Sorry, I encountered an issue processing your request.",
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, aiMessage]);
    } catch (err) {
      console.error(err);
      addToast("Failed to communicate with AI DevOps Assistant.", "error");
      
      const errorMessage: Message = {
        id: Math.random().toString(),
        sender: "ai",
        text: "I'm having trouble connecting to my models right now. Please verify your internet connection or check back in a moment.",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSendMessage(inputValue);
  };

  const handleQuickSuggest = (text: string) => {
    handleSendMessage(text);
  };

  const suggestions = [
    { text: "Explain my architecture", icon: Brain },
    { text: "Optimize cloud costs", icon: Sparkles },
    { text: "What is my container port?", icon: Terminal },
    { text: "Is my autoscaling active?", icon: HelpCircle },
  ];

  return (
    <>
      {/* Floating Trigger Button */}
      <div className="fixed bottom-6 right-6 z-50">
        <motion.button
          onClick={() => setIsOpen(!isOpen)}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          className={`w-14 h-14 rounded-full flex items-center justify-center text-white shadow-2xl relative transition-all duration-300 ${
            isOpen 
              ? "bg-zinc-800 border border-zinc-700 hover:bg-zinc-700" 
              : "bg-gradient-to-tr from-primary to-indigo-600 hover:from-primary-hover hover:to-indigo-500 glow-blue"
          }`}
        >
          <AnimatePresence mode="wait">
            {isOpen ? (
              <motion.div
                key="close"
                initial={{ rotate: -90, opacity: 0 }}
                animate={{ rotate: 0, opacity: 1 }}
                exit={{ rotate: 90, opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                <X size={22} />
              </motion.div>
            ) : (
              <motion.div
                key="open"
                initial={{ rotate: 90, opacity: 0 }}
                animate={{ rotate: 0, opacity: 1 }}
                exit={{ rotate: -90, opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="relative"
              >
                <MessageSquare size={22} />
                <span className="absolute -top-1.5 -right-1.5 w-3.5 h-3.5 bg-success rounded-full border-2 border-zinc-950 animate-pulse" />
              </motion.div>
            )}
          </AnimatePresence>
        </motion.button>
      </div>

      {/* Assistant Chat Panel */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: 30, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 30, scale: 0.95 }}
            transition={{ duration: 0.25, ease: "easeOut" }}
            className="fixed bottom-24 right-6 z-50 w-[380px] max-w-[calc(100vw-2rem)] h-[580px] max-h-[calc(100vh-8rem)] rounded-2xl border border-border bg-zinc-950/95 backdrop-blur-xl shadow-2xl flex flex-col overflow-hidden"
          >
            {/* Header */}
            <div className="bg-gradient-to-r from-primary/10 via-indigo-500/5 to-transparent border-b border-border p-4 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-8.5 h-8.5 rounded-lg bg-primary/10 border border-primary/30 flex items-center justify-center text-primary">
                  <Brain size={18} className="animate-pulse" />
                </div>
                <div>
                  <h3 className="text-xs font-bold text-foreground flex items-center gap-1.5">
                    ZeroOps AI Assistant
                  </h3>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
                    <span className="text-[9px] text-foreground-muted font-semibold uppercase tracking-wider">DevOps Team Online</span>
                  </div>
                </div>
              </div>
              <button 
                onClick={() => setIsOpen(false)}
                className="w-7 h-7 rounded-lg hover:bg-card-hover/60 flex items-center justify-center text-foreground-muted hover:text-foreground transition cursor-pointer"
              >
                <X size={16} />
              </button>
            </div>

            {/* Chat Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4 no-scrollbar">
              {messages.map((msg) => {
                const isUser = msg.sender === "user";
                return (
                  <div
                    key={msg.id}
                    className={`flex ${isUser ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`max-w-[85%] rounded-2xl px-4 py-3 text-xs leading-relaxed ${
                        isUser
                          ? "bg-primary text-white rounded-tr-none shadow-md shadow-primary/5"
                          : "bg-card border border-border text-foreground rounded-tl-none"
                      }`}
                    >
                      <p className="whitespace-pre-wrap">{msg.text}</p>
                      <span className={`block text-[9px] mt-1.5 text-right font-medium opacity-50 ${
                        isUser ? "text-white" : "text-foreground-muted"
                      }`}>
                        {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                  </div>
                );
              })}
              {loading && (
                <div className="flex justify-start">
                  <div className="bg-card border border-border text-foreground rounded-2xl rounded-tl-none px-4 py-3.5 text-xs flex items-center gap-2">
                    <Loader2 size={14} className="animate-spin text-primary" />
                    <span className="text-foreground-muted font-medium">Generating solution...</span>
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            {/* Suggestion Chips */}
            {messages.length === 1 && !loading && (
              <div className="px-4 py-2 border-t border-border bg-card/20 grid grid-cols-2 gap-2">
                {suggestions.map((sug, i) => {
                  const Icon = sug.icon;
                  return (
                    <button
                      key={i}
                      onClick={() => handleQuickSuggest(sug.text)}
                      className="flex items-center gap-1.5 p-2 rounded-xl border border-border/80 hover:border-primary/40 hover:bg-card-hover/40 text-left text-[10px] text-foreground-muted hover:text-foreground font-semibold transition cursor-pointer"
                    >
                      <Icon size={12} className="text-primary" />
                      <span className="truncate">{sug.text}</span>
                    </button>
                  );
                })}
              </div>
            )}

            {/* Input Form */}
            <form onSubmit={handleFormSubmit} className="p-4 border-t border-border bg-zinc-950 flex gap-2">
              <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                placeholder="Ask about architecture, costs..."
                disabled={loading}
                className="flex-1 bg-card border border-border rounded-xl px-3.5 py-2.5 text-xs text-foreground placeholder-foreground-muted focus:border-primary focus:outline-none disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={loading || !inputValue.trim()}
                className="w-10 h-10 rounded-xl bg-primary hover:bg-primary-hover text-white flex items-center justify-center disabled:opacity-50 disabled:bg-card transition glow-blue cursor-pointer"
              >
                <Send size={14} />
              </button>
            </form>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
