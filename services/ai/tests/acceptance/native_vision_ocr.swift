// macOS-only diagnostic. Raw OCR text must stay in a private temporary output.
import Foundation
import Vision
import ImageIO
let args = CommandLine.arguments
guard args.count == 3 else {
    fputs("Usage: native_vision_ocr.swift input-image output-json\n", stderr)
    exit(2)
}
guard !FileManager.default.fileExists(atPath: args[2]) else {
    fputs("Output already exists\n", stderr)
    exit(2)
}
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["zh-Hans", "en-US"]
request.usesLanguageCorrection = true
let started = Date()
let handler = VNImageRequestHandler(url: URL(fileURLWithPath: args[1]), options: [:])
do {
    let supported = try request.supportedRecognitionLanguages()
    try handler.perform([request])
    let lines: [[String: Any]] = (request.results ?? []).compactMap { item in
        guard let candidate = item.topCandidates(1).first else { return nil }
        return ["text": candidate.string, "confidence": candidate.confidence,
                "x": item.boundingBox.minX, "y": item.boundingBox.minY,
                "width": item.boundingBox.width, "height": item.boundingBox.height]
    }
    let result: [String: Any] = ["scope": "local OCR diagnostic, not production Harness", "request_revision": request.revision,
        "supported_languages": supported, "configured_languages": request.recognitionLanguages,
        "elapsed_ms": Int(Date().timeIntervalSince(started) * 1000), "lines": lines]
    let data = try JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted, .sortedKeys])
    try data.write(to: URL(fileURLWithPath: args[2]))
    print("Recognized \(lines.count) lines")
} catch { fputs("Vision OCR failed: \(error)\n", stderr); exit(1) }
