import Foundation

/// Splits a byte stream into `\n`-terminated lines. Works on bytes, so a multi-byte UTF-8
/// character split across chunks is reassembled before anyone decodes it.
public struct LineSplitter: Sendable {
    public init() {}

    /// The complete lines in the bytes fed so far, without their `\n`. A trailing partial
    /// line stays buffered for the next call.
    public mutating func feed(_ chunk: Data) -> [Data] {
        fatalError("unimplemented")
    }
}
