/**
 * System Role: Incremental Server-Sent Events parser for fetch() response bodies (POST cannot use EventSource).
 * Inputs: Text chunks decoded from a ReadableStream.
 * Outputs: Complete { event, data } frames; incomplete trailing text is kept for the next chunk.
 */

export interface SseFrame {
  event: string;
  data: string;
}

export function parseSseFrames(buffer: string): { frames: SseFrame[]; rest: string } {
  const blocks = buffer.replace(/\r\n/g, "\n").split("\n\n");
  const rest = blocks.pop() ?? "";
  const frames: SseFrame[] = [];

  for (const block of blocks) {
    let event = "message";
    const dataLines: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
    }
    if (dataLines.length > 0) frames.push({ event, data: dataLines.join("\n") });
  }
  return { frames, rest };
}

/**
 * Reads an SSE response body to completion, invoking onFrame for every frame in order.
 */
export async function readSseStream(
  body: ReadableStream<Uint8Array>,
  onFrame: (frame: SseFrame) => void
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const { frames, rest } = parseSseFrames(buffer);
    buffer = rest;
    frames.forEach(onFrame);
  }

  buffer += decoder.decode();
  parseSseFrames(buffer + "\n\n").frames.forEach(onFrame);
}
