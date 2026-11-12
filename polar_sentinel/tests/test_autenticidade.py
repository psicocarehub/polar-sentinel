"""Polar Sentinel: integridade de PDF assinado e proveniencia C2PA.

PDF assinado com certificado de teste: intacto (integridade confirmada com a
raiz de teste, inconclusivo com as raizes da ICP-Brasil) e alterado depois da
assinatura por revisao incremental (alteracao detectada, com a regiao). Foto
com manifesto C2PA: valido, declarando geracao por IA, e com um byte trocado.

Pedem pyhanko, cryptography, reportlab e pypdfium2; o C2PA pede c2pa-python.
"""

from __future__ import annotations

import datetime
import io
import json
import logging

import pytest

pytest.importorskip("pyhanko", exc_type=ImportError)
pytest.importorskip("reportlab", exc_type=ImportError)
pytest.importorskip("pypdfium2", exc_type=ImportError)

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec, rsa  # noqa: E402
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID  # noqa: E402

from polar_sentinel.reference.autenticidade import verificar_pdf, verificar_proveniencia  # noqa: E402

logging.disable(logging.CRITICAL)
AGORA = datetime.datetime.now(datetime.timezone.utc)


def _nome(cn: str) -> x509.Name:
    return x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, cn),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Teste"),
        ]
    )


@pytest.fixture(scope="module")
def certificado(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("cert")
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cert = (
        x509.CertificateBuilder()
        .subject_name(_nome("Advogado Exemplo"))
        .issuer_name(_nome("Advogado Exemplo"))
        .public_key(chave.public_key())
        .serial_number(1)
        .not_valid_before(AGORA - datetime.timedelta(days=1))
        .not_valid_after(AGORA + datetime.timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(True, True, False, False, False, True, True, False, False), critical=True
        )
        .sign(chave, hashes.SHA256())
    )
    (pasta / "k.pem").write_bytes(
        chave.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    (pasta / "c.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return pasta


def _assinado(pasta) -> bytes:
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import signers
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 760, "Peticao inicial. Valor da causa: R$ 18.400,00.")
    c.save()
    signer = signers.SimpleSigner.load(str(pasta / "k.pem"), str(pasta / "c.pem"))
    escritor = IncrementalPdfFileWriter(io.BytesIO(buf.getvalue()))
    return signers.sign_pdf(
        escritor, signers.PdfSignatureMetadata(field_name="Assinatura1"), signer=signer
    ).getvalue()


def _alterado(assinado: bytes) -> bytes:
    """Revisao incremental que cobre o valor e escreve outro por cima."""
    from pyhanko.pdf_utils import generic
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter

    escritor = IncrementalPdfFileWriter(io.BytesIO(assinado))
    pagina = escritor.root["/Pages"]["/Kids"][0]
    novo = escritor.add_object(
        generic.StreamObject(
            stream_data=b"q 1 1 1 rg 70 750 300 20 re f Q BT /F1 12 Tf 72 760 Td "
            b"(Valor da causa: R$ 184.000,00.) Tj ET"
        )
    )
    conteudos = pagina.raw_get("/Contents")
    pagina["/Contents"] = generic.ArrayObject([conteudos, novo])
    escritor.update_container(pagina)
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue()


def _raiz(pasta):
    from pyhanko.keys import load_cert_from_pemder

    return [load_cert_from_pemder(str(pasta / "c.pem"))]


def test_pdf_assinado_intacto(certificado):
    laudo = verificar_pdf(_assinado(certificado), raizes=_raiz(certificado))
    assert laudo.conclusao == "integridade_confirmada", laudo.observacoes
    assert laudo.assinaturas[0]["hash_confere"]


def test_pdf_assinado_fora_da_icp_brasil_e_inconclusivo(certificado):
    laudo = verificar_pdf(_assinado(certificado))
    assert laudo.conclusao == "inconclusivo"
    assert laudo.assinaturas[0]["cadeia_confiavel"] is False


def test_pdf_alterado_depois_da_assinatura(certificado):
    laudo = verificar_pdf(_alterado(_assinado(certificado)), raizes=_raiz(certificado))
    assert laudo.conclusao == "alteracao_detectada"
    assert laudo.assinaturas[0]["modificacao_depois"] == "alteração de conteúdo"
    regiao = laudo.alteracoes_visuais[0]["regiao_pt"]
    assert regiao[1] < 765 < regiao[3], "a regiao aponta a linha do valor da causa"


def test_pdf_sem_assinatura_e_inconclusivo():
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    canvas.Canvas(buf).save()
    assert verificar_pdf(buf.getvalue()).conclusao == "inconclusivo"


def test_c2pa_valido_alterado_e_ausente(tmp_path):
    c2pa = pytest.importorskip("c2pa", exc_type=ImportError)
    from PIL import Image

    ck, lk = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    ca = (
        x509.CertificateBuilder()
        .subject_name(_nome("AC Teste"))
        .issuer_name(_nome("AC Teste"))
        .public_key(ck.public_key())
        .serial_number(10)
        .not_valid_before(AGORA - datetime.timedelta(days=1))
        .not_valid_after(AGORA + datetime.timedelta(days=60))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(False, False, False, False, False, True, True, False, False),
            critical=True,
        )
        .sign(ck, hashes.SHA256())
    )
    folha = (
        x509.CertificateBuilder()
        .subject_name(_nome("Camera Teste"))
        .issuer_name(_nome("AC Teste"))
        .public_key(lk.public_key())
        .serial_number(11)
        .not_valid_before(AGORA - datetime.timedelta(days=1))
        .not_valid_after(AGORA + datetime.timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(True, False, False, False, False, False, False, False, False),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION]), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ck.public_key()), critical=False
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(lk.public_key()), critical=False)
        .sign(ck, hashes.SHA256())
    )
    cadeia = folha.public_bytes(serialization.Encoding.PEM) + ca.public_bytes(
        serialization.Encoding.PEM
    )
    chave = lk.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    foto = tmp_path / "foto.jpg"
    Image.new("RGB", (400, 300), (200, 210, 220)).save(foto, quality=90)
    assinada = tmp_path / "assinada.jpg"
    signer = c2pa.Signer.from_info(
        c2pa.C2paSignerInfo(c2pa.C2paSigningAlg.ES256, cadeia, chave, None)
    )
    manifesto = {
        "claim_generator": "teste/1.0",
        "title": "foto",
        "assertions": [
            {
                "label": "c2pa.actions",
                "data": {
                    "actions": [
                        {
                            "action": "c2pa.created",
                            "digitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia",
                        }
                    ]
                },
            }
        ],
    }
    with c2pa.Builder(json.dumps(manifesto)) as construtor:
        with open(foto, "rb") as origem, open(assinada, "w+b") as destino:
            construtor.sign(signer, "image/jpeg", origem, destino)
    alterada = tmp_path / "alterada.jpg"
    dados = bytearray(assinada.read_bytes())
    dados[-200] ^= 0xFF
    alterada.write_bytes(bytes(dados))

    assert verificar_proveniencia(foto).conclusao == "inconclusivo"
    valida = verificar_proveniencia(assinada)
    assert valida.proveniencia["declara_geracao_por_ia"] is True
    assert valida.conclusao == "inconclusivo", "assinante fora de lista de confianca"
    assert verificar_proveniencia(alterada).conclusao == "alteracao_detectada"
