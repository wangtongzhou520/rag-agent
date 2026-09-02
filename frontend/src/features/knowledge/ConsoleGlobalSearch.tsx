import { useQuery } from "@tanstack/react-query";
import { Database, FileText, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";

import { listKnowledgeBases, searchDocuments } from "@/features/knowledge/api";
import {
  buildConsoleSearchResults,
  type ConsoleSearchResult,
} from "@/features/knowledge/globalSearch";

function useDebouncedValue(value: string, delay: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [delay, value]);
  return debounced;
}

export function ConsoleGlobalSearch() {
  const navigate = useNavigate();
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [value, setValue] = useState("");
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const keyword = useDebouncedValue(value.trim(), 250);

  const basesQuery = useQuery({
    queryKey: ["console-global-search", "bases", keyword],
    queryFn: () => listKnowledgeBases(1, 5, keyword),
    enabled: open && Boolean(keyword),
    staleTime: 30_000,
  });
  const documentsQuery = useQuery({
    queryKey: ["console-global-search", "documents", keyword],
    queryFn: () => searchDocuments(keyword, 6),
    enabled: open && Boolean(keyword),
    staleTime: 30_000,
  });
  const results = useMemo(
    () => buildConsoleSearchResults(basesQuery.data?.records || [], documentsQuery.data || []),
    [basesQuery.data?.records, documentsQuery.data],
  );
  const loading = basesQuery.isFetching || documentsQuery.isFetching;
  const failed = basesQuery.isError && documentsQuery.isError;

  useEffect(() => setActiveIndex(-1), [keyword]);
  useEffect(() => {
    const close = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, []);
  useEffect(() => {
    const focusSearch = (event: globalThis.KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen(true);
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", focusSearch);
    return () => window.removeEventListener("keydown", focusSearch);
  }, []);

  const choose = (result: ConsoleSearchResult) => {
    setOpen(false);
    setActiveIndex(-1);
    inputRef.current?.blur();
    navigate(result.target);
  };
  const keyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      setOpen(false);
      inputRef.current?.blur();
      return;
    }
    if (!results.length) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => (index + 1) % results.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => (index <= 0 ? results.length - 1 : index - 1));
    } else if (event.key === "Enter" && activeIndex >= 0) {
      event.preventDefault();
      choose(results[activeIndex]);
    }
  };

  const showPanel = open && Boolean(value.trim());
  return (
    <div className="console-global-search" ref={rootRef}>
      <Search aria-hidden="true" />
      <input
        ref={inputRef}
        type="search"
        value={value}
        onChange={(event) => {
          setValue(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={keyDown}
        placeholder="搜索知识库和文档"
        aria-label="全局搜索"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={showPanel}
        aria-controls="console-global-search-results"
        aria-activedescendant={
          activeIndex >= 0 ? `global-search-${results[activeIndex]?.key}` : undefined
        }
      />

      {showPanel && (
        <div className="console-search-results" id="console-global-search-results" role="listbox">
          {!keyword || value.trim() !== keyword || loading ? (
            <div className="console-search-state">
              <span className="console-search-spinner" />
              正在搜索…
            </div>
          ) : failed ? (
            <div className="console-search-state console-search-state--error">
              搜索服务暂时不可用
            </div>
          ) : !results.length ? (
            <div className="console-search-state">没有找到“{keyword}”</div>
          ) : (
            <>
              {(["base", "document"] as const).map((kind) => {
                const items = results.filter((result) => result.kind === kind);
                if (!items.length) return null;
                return (
                  <section key={kind}>
                    <h2>{kind === "base" ? "知识库" : "文档"}</h2>
                    {items.map((result) => {
                      const index = results.indexOf(result);
                      const Icon = kind === "base" ? Database : FileText;
                      return (
                        <button
                          type="button"
                          role="option"
                          id={`global-search-${result.key}`}
                          aria-selected={activeIndex === index}
                          className={activeIndex === index ? "is-active" : ""}
                          key={result.key}
                          onMouseEnter={() => setActiveIndex(index)}
                          onClick={() => choose(result)}
                        >
                          <Icon aria-hidden="true" />
                          <span>
                            <strong>{result.label}</strong>
                            <small>{result.meta}</small>
                          </span>
                        </button>
                      );
                    })}
                  </section>
                );
              })}
              <footer>↑ ↓ 选择 · Enter 打开 · Esc 关闭</footer>
            </>
          )}
        </div>
      )}
    </div>
  );
}
