import {
  Save,
  FileCode,
  Users,
  Play,
  Loader2,
  GitCompare,
  ChevronDown,
} from "lucide-react";
import { Button } from "../ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";

interface EditorToolbarProps {
  onCompile: () => void;
  onDownloadTex: () => void;
  onUploadTex: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onSave: () => void;
  onSaveAsTemplate: () => void;
  onShareAnonymous: () => void;
  isCompiling: boolean;
  isSaving: boolean;
  hasResumeId: boolean;
  showDiff: boolean;
  onToggleDiff: () => void;
  hasDiff: boolean;
  isStreamingLatex?: boolean;
}

export function EditorToolbar({
  onCompile,
  onDownloadTex,
  onUploadTex,
  onSave,
  onSaveAsTemplate,
  onShareAnonymous,
  isCompiling,
  isSaving,
  hasResumeId,
  showDiff,
  onToggleDiff,
  hasDiff,
  isStreamingLatex = false,
}: EditorToolbarProps) {
  return (
    <div className="flex items-center gap-1 sm:gap-2">
      {/* MOBILE: Save Dropdown */}
      <div className="flex sm:hidden">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className="font-sans text-[12px] h-8 rounded-md border-border px-2"
              disabled={isSaving || !hasResumeId}
            >
              {isSaving ? (
                <Loader2
                  size={13}
                  className="animate-spin text-muted-foreground mr-1"
                />
              ) : (
                <Save size={13} className="mr-1" />
              )}
              <span>Save</span>
              <ChevronDown size={13} className="ml-1 opacity-50" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuItem onClick={onSave}>
              Save to Library
            </DropdownMenuItem>
            <DropdownMenuItem onClick={onSaveAsTemplate}>
              Save as Template
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={onShareAnonymous}
              disabled={!hasResumeId}
            >
              Share Anonymous
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* DESKTOP: Save Buttons */}
      <div className="hidden sm:flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          className="font-sans text-[12px] h-8 rounded-md border-border"
          onClick={onSave}
          disabled={isSaving || !hasResumeId}
        >
          {isSaving ? (
            <Loader2 size={13} className="animate-spin text-muted-foreground" />
          ) : (
            <Save size={13} />
          )}
          <span>Save</span>
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="font-sans text-[12px] h-8 rounded-md border-border"
          onClick={onSaveAsTemplate}
        >
          <FileCode size={13} />
          <span>As Template</span>
        </Button>
      </div>

      {hasDiff && (
        <Button
          variant={showDiff ? "default" : "outline"}
          size="sm"
          className="font-sans text-[12px] h-8 rounded-md border-border px-2 sm:px-3"
          onClick={onToggleDiff}
        >
          <GitCompare size={13} />
          <span className="hidden sm:inline ml-1">
            {showDiff ? "Hide Changes" : "Show Changes"}
          </span>
          <span className="inline sm:hidden ml-1">Diff</span>
        </Button>
      )}

      {/* DESKTOP: Share Button */}
      <Button
        variant="outline"
        size="sm"
        className="hidden sm:flex font-sans text-[12px] h-8 rounded-md border-border"
        onClick={onShareAnonymous}
        disabled={!hasResumeId}
      >
        <Users size={13} />
        <span>Share Anonymous</span>
      </Button>

      <div className="h-4 w-px bg-border mx-1" />

      {/* MOBILE: TeX Dropdown */}
      <div className="flex sm:hidden">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              className="font-sans text-[12px] h-8 text-muted-foreground hover:text-foreground px-2"
            >
              <span>TeX</span>
              <ChevronDown size={13} className="ml-1 opacity-50" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <div className="relative">
              <input
                type="file"
                accept=".tex"
                onChange={onUploadTex}
                className="absolute inset-0 opacity-0 cursor-pointer w-full h-full z-10"
                title="Upload .tex file"
              />
              <DropdownMenuItem onSelect={(e) => e.preventDefault()}>
                Upload .tex
              </DropdownMenuItem>
            </div>
            <DropdownMenuItem onClick={onDownloadTex}>
              Download .tex
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* DESKTOP: TeX Buttons */}
      <div className="hidden sm:flex items-center gap-0">
        <div className="relative overflow-hidden">
          <input
            type="file"
            accept=".tex"
            onChange={onUploadTex}
            className="absolute inset-0 opacity-0 cursor-pointer w-full h-full z-10"
            title="Upload .tex file"
          />
          <Button
            variant="ghost"
            size="sm"
            className="font-sans text-[12px] h-8 text-muted-foreground hover:text-foreground px-2 pointer-events-none"
          >
            Upload .tex
          </Button>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="font-sans text-[12px] h-8 text-muted-foreground hover:text-foreground px-2"
          onClick={onDownloadTex}
        >
          Download .tex
        </Button>
      </div>

      <Button
        variant="default"
        size="sm"
        className="font-sans text-[12px] font-semibold h-8 rounded-md px-2 sm:px-3 ml-auto"
        onClick={onCompile}
        disabled={isCompiling || isStreamingLatex}
      >
        {isCompiling ? (
          <>
            <Loader2 size={13} className="animate-spin" />
            <span className="hidden sm:inline ml-1">Compiling...</span>
          </>
        ) : isStreamingLatex ? (
          <>
            <Loader2 size={13} className="animate-spin" />
            <span className="hidden sm:inline ml-1">AI Writing...</span>
            <span className="inline sm:hidden ml-1">Writing</span>
          </>
        ) : (
          <>
            <Play size={12} fill="currentColor" />
            <span className="hidden sm:inline ml-1">Compile PDF</span>
            <span className="inline sm:hidden ml-1">Compile</span>
          </>
        )}
      </Button>
    </div>
  );
}
