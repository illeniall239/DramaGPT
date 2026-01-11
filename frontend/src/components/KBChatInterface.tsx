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
    BookOpen,
    AlertCircle
} from 'lucide-react';
import {
    loadKBChatMessages,
    saveChatMessages as saveKBChatMessages,
    updateChatTitle,
    generateChatTitle,
    streamQueryKnowledgeBase
} from '@/utils/api';
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
                } catch (error) {
                    console.error('Failed to update chat title:', error);
                }
            }).catch(err => console.error('Title generation failed:', err));
        }

        try {
            let finalContent = '';
            let finalSources: KBSource[] = [];
            let finalVisualization: any = null;

            await streamQueryKnowledgeBase(
                kbId,
                userInput,
                chatId,
                (chunk) => {
                    if (chunk.content) {
                        finalContent = chunk.content;
                        setMessages(prev => {
                            const newMessages = [...prev];
                            const last = newMessages[newMessages.length - 1];

                            // If no assistant message exists yet, create one
                            if (!last || last.role !== 'assistant') {
                                newMessages.push({
                                    role: 'assistant',
                                    content: chunk.content,
                                    timestamp: Date.now(),
                                    isTyping: !chunk.is_final
                                });
                            } else {
                                // Update existing assistant message
                                last.content = chunk.content;
                                last.isTyping = !chunk.is_final;
                                if (chunk.is_final) {
                                    last.sources = chunk.sources;
                                    last.visualization = chunk.visualization;
                                }
                            }
                            return newMessages;
                        });
                    } else if (chunk.is_final) {
                        finalContent = chunk.content || finalContent;
                        finalSources = chunk.sources || [];
                        finalVisualization = chunk.visualization || null;
                    } else if (chunk.error) {
                        throw new Error(chunk.error);
                    }
                }
            );

            // Final sync of history
            const updatedAssistantMessage: ChatMessage = {
                role: 'assistant',
                content: finalContent,
                timestamp: Date.now(),
                visualization: finalVisualization,
            };
            if (finalSources.length > 0) {
                (updatedAssistantMessage as any).sources = finalSources;
            }

            const updatedMessages = [...messages, userMessage, updatedAssistantMessage];
            try {
                await saveKBChatMessages(chatId, updatedMessages);
            } catch (saveError) {
                console.error('Failed to save messages:', saveError);
            }

        } catch (error) {
            console.error('Failed to query KB:', error);

            const errorMsg = error instanceof Error ? error.message : 'Failed to process your question.';
            const isRateLimit = errorMsg.includes('429') || errorMsg.toLowerCase().includes('quota') || errorMsg.toLowerCase().includes('rate limit');

            const errorMessage: ChatMessage = {
                role: 'assistant',
                content: isRateLimit
                    ? `### API Rate Limit Reached\n\nYour Gemini API quota has been exceeded. This usually happens on the free tier when sending too many requests in a short time.\n\n**Please wait 30-60 seconds before trying again.**`
                    : `❌ Error: ${errorMsg}`,
                timestamp: Date.now(),
                isError: true,
                errorType: isRateLimit ? 'rate_limit' : 'generic'
            };

            setMessages(prev => {
                const newMessages = [...prev];
                const last = newMessages[newMessages.length - 1];

                // If assistant message doesn't exist (because we removed placeholder), add error message
                if (!last || last.role !== 'assistant') {
                    newMessages.push(errorMessage);
                } else {
                    // Replace placeholder with error
                    newMessages[newMessages.length - 1] = errorMessage;
                }
                return newMessages;
            });

            const updatedMessages = [...messages, userMessage, errorMessage];
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
                    <div className="h-full flex flex-col items-center justify-center text-center px-4 sm:px-8 py-12">
                        <BookOpen className="w-10 h-10 sm:w-12 sm:h-12 text-primary/60 mb-4" />
                        <h3 className="text-lg sm:text-xl font-display font-semibold text-foreground mb-2">
                            Start a Conversation
                        </h3>
                        <p className="text-xs sm:text-sm text-muted-foreground max-w-md mb-6 leading-relaxed">
                            Ask questions about your uploaded documents, run analytics on your data,
                            or request predictions based on your knowledge base.
                        </p>
                        <div className="space-y-2 w-full max-w-sm sm:max-w-md">
                            <p className="text-xs font-medium text-foreground mb-2 text-left">
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
                            className={`w-full ${message.role === 'user' ? 'bg-white' : 'bg-muted/20'
                                } border-b border-border/50`}
                        >
                            <div className="max-w-4xl mx-auto px-4 sm:px-6 py-4 sm:py-6">
                                <div
                                    className={`flex gap-3 sm:gap-4 ${message.role === 'user' ? 'flex-row-reverse' : 'flex-row'
                                        }`}
                                >
                                    {/* Avatar */}
                                    <div className="flex-shrink-0">
                                        <div className={`w-7 h-7 sm:w-8 sm:h-8 rounded-full flex items-center justify-center text-[10px] sm:text-xs font-semibold ${message.role === 'user'
                                            ? 'bg-primary text-white'
                                            : 'bg-accent text-accent-foreground'
                                            }`}>
                                            {message.role === 'user' ? 'U' : 'AI'}
                                        </div>
                                    </div>

                                    {/* Content */}
                                    <div className={`flex-1 min-w-0 ${message.role === 'user' ? 'text-right' : ''
                                        }`}>
                                        {/* Message Content */}
                                        <div className={`prose prose-sm max-w-none markdown-content ${message.isError ? 'text-red-600' : ''}`}>
                                            {message.errorType === 'rate_limit' ? (
                                                <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-4 flex gap-3">
                                                    <AlertCircle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
                                                    <div className="text-sm text-red-800">
                                                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                                            {message.content}
                                                        </ReactMarkdown>
                                                    </div>
                                                </div>
                                            ) : (
                                                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                                    {message.content}
                                                </ReactMarkdown>
                                            )}
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
                        <div className="max-w-4xl mx-auto px-4 sm:px-6 py-4 sm:py-6">
                            <div className="flex gap-3 sm:gap-4">
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
            <div className="border-t border-border bg-white px-2 sm:px-4 py-3 sm:py-4">
                <div className="max-w-4xl mx-auto">
                    <div className="flex gap-2 sm:gap-3 items-end">
                        <textarea
                            ref={inputRef}
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="Ask a question..."
                            className="flex-1 px-3 sm:px-4 py-2 sm:py-3 border border-border rounded-xl bg-white text-foreground placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary resize-none shadow-sm text-sm sm:text-base min-h-[44px] sm:min-h-[50px] max-h-32"
                            rows={1}
                            disabled={isProcessing}
                        />
                        <button
                            onClick={handleSendMessage}
                            disabled={!input.trim() || isProcessing}
                            className="p-2.5 sm:px-4 sm:py-3 bg-primary text-white rounded-xl hover:bg-primary-hover disabled:opacity-40 disabled:cursor-not-allowed transition-all flex items-center justify-center shadow-sm"
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
