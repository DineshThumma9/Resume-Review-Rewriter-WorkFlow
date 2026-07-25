"use client";

import { IconSend, IconLoader2 } from "@tabler/icons-react";
import type React from "react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useResumeStore } from "../store/resumeStore";
import { modifyResume } from "../apis/resumes";

interface AiProps {
  provider?: string;
  model?: string;
}

export default function Ai({
  provider = "groq",
  model = "llama-3.3-70b-versatile",
}: AiProps) {
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { latexCode, setResumeState } = useResumeStore();
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!message.trim() || loading) return;

    setLoading(true);
    setError(null);
    const instruction = message;
    setMessage("");

    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }

    try {
      let accumulated = "";
      setResumeState({ isStreamingLatex: true });
      await modifyResume(latexCode, instruction, provider, model, (ev) => {
        if (ev.event === "chunk" && ev.text) {
          accumulated += ev.text;
          setResumeState({ latexCode: accumulated, isStreamingLatex: true });
        } else if (ev.event === "error" && ev.message) {
          setError(ev.message);
        }
      });
    } catch (err: any) {
      console.error(err);
      setError(err?.message || "An error occurred while modifying the resume.");
    } finally {
      setLoading(false);
      setResumeState({ isStreamingLatex: false });
    }
  };

  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setMessage(e.target.value);

    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e as any);
    }
  };

  return (
    <div className="w-full">
      {error && (
        <div className="max-w-2xl mx-auto mb-2 p-2 bg-destructive/15 border border-destructive/25 text-destructive rounded-lg text-xs flex justify-between items-center animate-in fade-in duration-200">
          <span>{error}</span>
          <button
            type="button"
            onClick={() => setError(null)}
            className="hover:text-destructive/80 font-bold ml-2"
          >
            ✕
          </button>
        </div>
      )}

      <form
        className="flex items-end gap-2 max-w-2xl mx-auto border border-border/40 rounded-2xl p-1.5 bg-background/20 backdrop-blur-md shadow-lg focus-within:border-primary/50 focus-within:bg-background/40 transition-all"
        onSubmit={handleSubmit}
      >
        <Textarea
          className="scrollbar-thin min-h-10 max-h-52 flex-1 resize-none border-0 p-2 text-sm placeholder:text-muted-foreground focus-visible:ring-0 focus-visible:ring-offset-0 bg-transparent"
          onChange={handleTextareaChange}
          onKeyDown={handleKeyDown}
          placeholder={loading ? "AI is rewriting..." : "Ask AI to modify..."}
          ref={textareaRef}
          rows={1}
          value={message}
          disabled={loading}
        />

        {(message.trim() || loading) && (
          <Button
            aria-label="Send message"
            className="rounded-xl h-10 w-10 shrink-0 mb-0.5 mr-0.5"
            size="icon"
            type="submit"
            disabled={loading}
          >
            {loading ? (
              <IconLoader2 className="size-4 animate-spin" />
            ) : (
              <IconSend className="size-4" />
            )}
          </Button>
        )}
      </form>
    </div>
  );
}
