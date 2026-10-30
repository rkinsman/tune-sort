import Foundation

/// True for playlists TuneSort creates: `Bass – X` or `Bass 5-String – X` (en dash, U+2013);
/// likewise `Guitar`. `X` must be non-empty.
public func isTuningPlaylist(_ name: String, for i: Instrument) -> Bool {
    let word = i.rawValue.capitalized
    return name.range(of: "^\(word)( [0-9]+-String)? \u{2013} .+", options: .regularExpression) != nil
}
