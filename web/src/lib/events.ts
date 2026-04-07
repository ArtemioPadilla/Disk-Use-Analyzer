type Listener = (data?: any) => void;

export function emit(event: string, data?: any): void {
  window.dispatchEvent(new CustomEvent(event, { detail: data }));
}

export function on(event: string, listener: Listener): () => void {
  const handler = (e: Event) => listener((e as CustomEvent).detail);
  window.addEventListener(event, handler);
  return () => {
    window.removeEventListener(event, handler);
  };
}
