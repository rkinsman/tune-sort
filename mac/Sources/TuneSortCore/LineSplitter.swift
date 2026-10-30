import Foundation

/// Splits a byte stream into `\n`-terminated lines. Works on bytes, so a multi-byte UTF-8
/// character split across chunks is reassembled before anyone decodes it.
public struct LineSplitter: Sendable {
    private var buffer = Data()

    public init() {}

    /// The complete lines in the bytes fed so far, without their `\n`. A trailing partial
    /// line stays buffered for the next call.
    public mutating func feed(_ chunk: Data) -> [Data] {
        buffer.append(chunk)
        var lines: [Data] = []
        var start = buffer.startIndex
        while let newline = buffer[start...].firstIndex(of: UInt8(ascii: "\n")) {
            lines.append(Data(buffer[start..<newline]))
            start = buffer.index(after: newline)
        }
        if start != buffer.startIndex {
            buffer = Data(buffer[start...])
        }
        return lines
    }

    /// Takes whatever partial line is buffered (used at end of stream); nil if none.
    mutating func flush() -> Data? {
        guard !buffer.isEmpty else { return nil }
        defer { buffer = Data() }
        return buffer
    }
}
