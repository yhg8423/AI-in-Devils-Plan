import Foundation
import Translation

@main
struct TranslateKorean {
    static func main() async {
        let source = Locale.Language(identifier: "ko")
        let target = Locale.Language(identifier: "en")
        guard await LanguageAvailability().status(from: source, to: target) == .installed else {
            FileHandle.standardError.write(Data("Install the Korean and English languages in macOS Translate first.\n".utf8))
            exit(1)
        }

        let session = TranslationSession(installedSource: source, target: target)
        let decoder = JSONDecoder()
        let encoder = JSONEncoder()
        do {
            while let line = readLine() {
                let texts = try decoder.decode([String].self, from: Data(line.utf8))
                let batch = texts.enumerated().map { index, text in
                    TranslationSession.Request(sourceText: text, clientIdentifier: String(index))
                }
                let responses = try await session.translations(from: batch)
                var translations = Array<String?>(repeating: nil, count: texts.count)
                for response in responses {
                    guard let identifier = response.clientIdentifier,
                          let index = Int(identifier),
                          translations.indices.contains(index),
                          translations[index] == nil else {
                        throw TranslationBatchError.invalidResponse
                    }
                    translations[index] = response.targetText
                }
                guard translations.allSatisfy({ $0 != nil }) else {
                    throw TranslationBatchError.invalidResponse
                }
                var output = try encoder.encode(translations)
                output.append(0x0a)
                FileHandle.standardOutput.write(output)
            }
        } catch {
            FileHandle.standardError.write(Data("Korean-to-English translation failed: \(error)\n".utf8))
            exit(1)
        }
    }
}

enum TranslationBatchError: Error {
    case invalidResponse
}
