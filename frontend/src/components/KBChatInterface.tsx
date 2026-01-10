'use client';

import React, { useState, useRef, useEffect } from 'react';
import {
    Send,
    Loader2,
    FileText,
    BarChart3,
    ExternalLink,
    ChevronDown,
    ChevronUp,
    BookOpen
} from 'lucide-react';
import { queryKB, loadKBChatMessages, saveKBChatMessages, updateChatTitle, generateChatTitle } from '@/utils/api';
import { ChatMessage, KBQueryResponse, KBSource } from '@/types';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import Image from 'next/image';
import { API_BASE_URL } from '@/config';

interface KBChatInterfaceProps {
    kbId: string;
    chatId: string;
    kbName: string;
}

export default function KBChatInterface({
    kbId,
    chatId,
    kbName
}: KBChatInterfaceProps) {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [input, setInput] = useState('');
    const [isProcessing, setIsProcessing] = useState(false);
    const [expandedSources, setExpandedSources] = useState<Set<number>>(new Set());
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLTextAreaElement>(null);

    // Auto-scroll to bottom on new messages
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    // Auto-focus input on mount
    useEffect(() => {
        inputRef.current?.focus();
    }, []);

    // Load messages when chat is opened
    useEffect(() => {
        async function loadMessages() {
            try {
                const loadedMessages = await loadKBChatMessages(chatId);
                if (loadedMessages && loadedMessages.length > 0) {
                    setMessages(loadedMessages);
                    console.log('✅ Loaded', loadedMessages.length, 'messages from chat');
                }
            } catch (error) {
                console.error('Failed to load chat messages:', error);
            }
        }

        // Reset messages and load from database
        setMessages([]);
        loadMessages();
    }, [chatId]);

    async function handleSendMessage() {
        if (!input.trim() || isProcessing) return;

        const isFirstMessage = messages.length === 0;
        const userInput = input; // Store input before clearing

        const userMessage: ChatMessage = {
            role: 'user',
            content: userInput,
            timestamp: Date.now()
        };

        setMessages(prev => [...prev, userMessage]);
        setInput('');
        setIsProcessing(true);

        // Generate and update title for first message (non-blocking)
        if (isFirstMessage) {
            generateChatTitle(userInput).then(async (title) => {
                try {
                    await updateChatTitle(chatId, title);
                    console.log('✅ Chat title auto-generated:', title);
                } catch (error) {
                    console.error('Failed to update chat title:', error);
                }
            }).catch(err => console.error('Title generation failed:', err));
        }

        try {
            const response: KBQueryResponse = await queryKB(kbId, userInput, chatId);

            // Create assistant message
            const assistantMessage: ChatMessage = {
                role: 'assistant',
                content: response.response,
                timestamp: Date.now(),
                visualization: response.visualization,
            };

            // Add sources metadata (custom field)
            if (response.sources && response.sources.length > 0) {
                (assistantMessage as any).sources = response.sources;
            }

            const updatedMessages = [...messages, userMessage, assistantMessage];
            setMessages(updatedMessages);

            // Save messages to database
            try {
                await saveKBChatMessages(chatId, updatedMessages);
            } catch (saveError) {
                console.error('Failed to save messages:', saveError);
            }
        } catch (error) {
            console.error('Failed to query KB:', error);

            const errorMessage: ChatMessage = {
                role: 'assistant',
                content: `❌ Error: ${error instanceof Error ? error.message : 'Failed to process your question. Please try again.'}`,
                timestamp: Date.now()
            };

            const updatedMessages = [...messages, userMessage, errorMessage];
            setMessages(updatedMessages);

            // Save messages even if query failed
            try {
                await saveKBChatMessages(chatId, updatedMessages);
            } catch (saveError) {
                console.error('Failed to save messages:', saveError);
            }
        } finally {
            setIsProcessing(false);
        }
    }

    function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSendMessage();
        }
    }

    function toggleSourceExpansion(messageIndex: number) {
        setExpandedSources(prev => {
            const updated = new Set(prev);
            if (updated.has(messageIndex)) {
                updated.delete(messageIndex);
            } else {
                updated.add(messageIndex);
            }
            return updated;
        });
    }

    return (
        <div className="h-full flex flex-col bg-white">
            {/* Messages */}
            <div className="flex-1 overflow-y-auto">
                {messages.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center text-center px-8 py-12">
                        <BookOpen className="w-12 h-12 text-primary/60 mb-4" />
                        <h3 className="text-xl font-display font-semibold text-foreground mb-2">
                            Start a Conversation
                        </h3>
                        <p className="text-sm text-muted-foreground max-w-md mb-6 leading-relaxed">
                            Ask questions about your uploaded documents, run analytics on your data,
                            or request predictions based on your knowledge base.
                        </p>
                        <div className="space-y-2 w-full max-w-md">
                            <p className="text-xs font-medium text-foreground mb-3 text-left">
                                Try asking:
                            </p>
                            <button
                                onClick={() => setInput('What are the main topics in these documents?')}
                                className="w-full text-left px-4 py-3 bg-white border border-border rounded-lg text-sm text-foreground hover:bg-muted/50 transition-colors"
                            >
                                "What are the main topics in these documents?"
                            </button>
                            <button
                                onClick={() => setInput('Summarize the key findings from page 5')}
                                className="w-full text-left px-4 py-3 bg-white border border-border rounded-lg text-sm text-foreground hover:bg-muted/50 transition-colors"
                            >
                                "Summarize the key findings from page 5"
                            </button>
                            <button
                                onClick={() => setInput('What trends can you identify in the data?')}
                                className="w-full text-left px-4 py-3 bg-white border border-border rounded-lg text-sm text-foreground hover:bg-muted/50 transition-colors"
                            >
                                "What trends can you identify in the data?"
                            </button>
                        </div>
                    </div>
                ) : (
                    messages.map((message, index) => (
                        <div
                            key={index}
                            className={`w-full ${
                                message.role === 'user' ? 'bg-white' : 'bg-muted/20'
                            } border-b border-border/50`}
                        >
                            <div className="max-w-3xl mx-auto px-6 py-6">
                                <div
                                    className={`flex gap-4 ${
                                        message.role === 'user' ? 'flex-row-reverse' : 'flex-row'
                                    }`}
                                >
                                    {/* Avatar */}
                                    <div className="flex-shrink-0">
                                        <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold ${
                                            message.role === 'user'
                                                ? 'bg-primary text-white'
                                                : 'bg-accent text-accent-foreground'
                                        }`}>
                                            {message.role === 'user' ? 'U' : 'AI'}
                                        </div>
                                    </div>

                                    {/* Content */}
                                    <div className={`flex-1 min-w-0 ${
                                        message.role === 'user' ? 'text-right' : ''
                                    }`}>
                                        {/* Message Content */}
                                        <div className="prose prose-sm max-w-none markdown-content">
                                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                                {message.content}
                                            </ReactMarkdown>
                                        </div>

                                        {/* Visualization */}
                                        {message.visualization && (
                                            <div className="mt-4 border border-border rounded-xl overflow-hidden shadow-sm bg-white">
                                                {message.visualization.type === 'matplotlib_figure' ? (
                                                    <Image
                                                        src={`${API_BASE_URL}${message.visualization.path}`}
                                                        alt="Visualization"
                                                        width={600}
                                                        height={400}
                                                        className="w-full h-auto"
                                                    />
                                                ) : (
                                                    <iframe
                                                        src={`${API_BASE_URL}${message.visualization.path}`}
                                                        className="w-full h-96"
                                                        title="Interactive Visualization"
                                                    />
                                                )}
                                            </div>
                                        )}

                                        {/* Source Citations */}
                                        {message.role === 'assistant' && (message as any).sources && (
                                            <div className="mt-4 pt-4 border-t border-border/50">
                                                <button
                                                    onClick={() => toggleSourceExpansion(index)}
                                                    className="flex items-center gap-2 text-sm font-medium text-foreground hover:text-primary transition-colors"
                                                >
                                                    <FileText className="w-4 h-4" />
                                                    <span>
                                                        {(message as any).sources.length}{' '}
                                                        {(message as any).sources.length === 1 ? 'Source' : 'Sources'}
                                                    </span>
                                                    {expandedSources.has(index) ? (
                                                        <ChevronUp className="w-4 h-4" />
                                                    ) : (
                                                        <ChevronDown className="w-4 h-4" />
                                                    )}
                                                </button>

                                                {expandedSources.has(index) && (
                                                    <div className="mt-3 space-y-2">
                                                        {((message as any).sources as KBSource[]).map((source) => (
                                                            <div
                                                                key={source.number}
                                                                className="p-3 bg-muted/30 border border-border rounded-lg"
                                                            >
                                                                <div className="flex items-start justify-between mb-2">
                                                                    <div className="flex items-center gap-2">
                                                                        <span className="text-xs font-semibold text-white bg-primary px-2 py-1 rounded">
                                                                            Source {source.number}
                                                                        </span>
                                                                        <span className="text-xs text-muted-foreground">
                                                                            Relevance: {(source.similarity * 100).toFixed(1)}%
                                                                        </span>
                                                                    </div>
                                                                </div>
                                                                <p className="text-sm text-foreground/80 leading-relaxed">
                                                                    {source.content}
                                                                </p>
                                                                {source.metadata && (
                                                                    <div className="mt-2 text-xs text-muted-foreground">
                                                                        {source.metadata.page && (
                                                                            <span>Page {source.metadata.page}</span>
                                                                        )}
                                                                    </div>
                                                                )}
                                                            </div>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>
                                        )}

                                        {/* Timestamp */}
                                        <div className="mt-3 text-xs text-muted-foreground">
                                            {new Date(message.timestamp || Date.now()).toLocaleTimeString([], {
                                                hour: '2-digit',
                                                minute: '2-digit'
                                            })}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    ))
                )}

                {/* Typing Indicator */}
                {isProcessing && (
                    <div className="w-full bg-muted/20 border-b border-border/50">
                        <div className="max-w-3xl mx-auto px-6 py-6">
                            <div className="flex gap-4">
                                <div className="flex-shrink-0">
                                    <div className="w-8 h-8 rounded-full bg-accent text-accent-foreground flex items-center justify-center text-xs font-semibold">
                                        AI
                                    </div>
                                </div>
                                <div className="flex items-center gap-2 pt-1">
                                    <Loader2 className="w-4 h-4 animate-spin text-primary" />
                                    <span className="text-sm text-muted-foreground">
                                        Analyzing...
                                    </span>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>

            {/* Input Area */}
            <div className="border-t border-border bg-white px-4 py-4">
                <div className="max-w-3xl mx-auto">
                    <div className="flex gap-3 items-end">
                        <textarea
                            ref={inputRef}
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="Ask a question about your knowledge base..."
                            className="flex-1 px-4 py-3 border border-border rounded-xl bg-white text-foreground placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary resize-none shadow-sm"
                            rows={1}
                            disabled={isProcessing}
                        />
                        <button
                            onClick={handleSendMessage}
                            disabled={!input.trim() || isProcessing}
                            className="px-4 py-3 bg-primary text-white rounded-xl hover:bg-primary-hover disabled:opacity-40 disabled:cursor-not-allowed transition-all flex items-center justify-center shadow-sm"
                        >
                            {isProcessing ? (
                                <Loader2 className="w-5 h-5 animate-spin" />
                            ) : (
                                <Send className="w-5 h-5" />
                            )}
                        </button>
                    </div>
                    <p className="text-xs text-muted-foreground mt-2 text-center">
                        Press Enter to send, Shift+Enter for new line
                    </p>
                </div>
            </div>
        </div>
    );
}
