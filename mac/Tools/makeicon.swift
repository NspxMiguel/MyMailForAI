// Desenha Resources/icon-1024.png. Vetor na mão, não arte gerada: o ícone é um
// envelope com a barra de menus por cima — que é literalmente o que o app é.
import AppKit
import Foundation

let lado: CGFloat = 1024
let imagem = NSImage(size: NSSize(width: lado, height: lado))
imagem.lockFocus()

// fundo: quadrado arredondado escuro, no raio que a Apple usa (~22,37%)
let margem: CGFloat = 80
let caixa = NSRect(x: margem, y: margem, width: lado - margem * 2, height: lado - margem * 2)
let raio = caixa.width * 0.2237
let fundo = NSBezierPath(roundedRect: caixa, xRadius: raio, yRadius: raio)
let gradiente = NSGradient(colors: [NSColor(calibratedRed: 0.09, green: 0.10, blue: 0.12, alpha: 1),
                                    NSColor(calibratedRed: 0.15, green: 0.16, blue: 0.19, alpha: 1)])!
gradiente.draw(in: fundo, angle: 90)

let ambar = NSColor(calibratedRed: 0.96, green: 0.62, blue: 0.04, alpha: 1)

// o envelope
let env = NSRect(x: 288, y: 330, width: 448, height: 316)
let corpo = NSBezierPath(roundedRect: env, xRadius: 26, yRadius: 26)
corpo.lineWidth = 34
ambar.setStroke()
corpo.stroke()

// a aba, como a linha que um cliente de e-mail desenha
let aba = NSBezierPath()
aba.move(to: NSPoint(x: env.minX + 26, y: env.maxY - 30))
aba.line(to: NSPoint(x: env.midX, y: env.midY + 14))
aba.line(to: NSPoint(x: env.maxX - 26, y: env.maxY - 30))
aba.lineWidth = 34
aba.lineCapStyle = .round
aba.lineJoinStyle = .round
aba.stroke()

// a barra de menus por cima: é onde o app vive, e é o que o diferencia
let barra = NSRect(x: caixa.minX, y: caixa.maxY - 118, width: caixa.width, height: 118)
let recorte = NSBezierPath(roundedRect: caixa, xRadius: raio, yRadius: raio)
NSGraphicsContext.saveGraphicsState()
recorte.addClip()
NSColor(calibratedWhite: 1, alpha: 0.10).setFill()
barra.fill()
NSColor(calibratedWhite: 1, alpha: 0.55).setFill()
// três pontinhos, do jeito que os itens aparecem na barra
for i in 0..<3 {
    let ponto = NSRect(x: caixa.maxX - 96 - CGFloat(i) * 76, y: barra.midY - 13, width: 26, height: 26)
    NSBezierPath(ovalIn: ponto).fill()
}
NSGraphicsContext.restoreGraphicsState()

// o ponto vermelho da fila esperando confirmação
NSColor(calibratedRed: 0.91, green: 0.30, blue: 0.24, alpha: 1).setFill()
NSBezierPath(ovalIn: NSRect(x: env.maxX - 58, y: env.maxY - 58, width: 116, height: 116)).fill()

imagem.unlockFocus()

guard let tiff = imagem.tiffRepresentation,
      let rep = NSBitmapImageRep(data: tiff),
      let png = rep.representation(using: .png, properties: [:]) else {
    FileHandle.standardError.write(Data("não consegui gerar o PNG\n".utf8))
    exit(1)
}
let destino = URL(fileURLWithPath: "Resources/icon-1024.png")
try! png.write(to: destino)
print("==> \(destino.path)")
