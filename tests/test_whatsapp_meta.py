import io
import json
import ssl
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

import whatsapp_meta

CONFIG = dict(api_version='v23.0',phone_number_id='123456789',recipient='5511999999999',
              template_name='velosonet_alerta',language='pt_BR')
TOKEN = 'fake_meta_token_for_tests_only_123456'


class WhatsAppMetaTests(unittest.TestCase):
    def response(self,payload):
        response=Mock(); response.read.return_value=json.dumps(payload).encode()
        response.__enter__=Mock(return_value=response); response.__exit__=Mock(return_value=False)
        return response

    def test_official_template_request_has_one_body_parameter_and_no_token_in_url(self):
        with patch.object(whatsapp_meta,'build_opener') as builder:
            builder.return_value.open.return_value=self.response({'messages':[{'id':'simulated-wamid'}]})
            self.assertEqual(whatsapp_meta.send(CONFIG,TOKEN,'Queda\nTeste\t   de envio'),'simulated-wamid')
        request=builder.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url,'https://graph.facebook.com/v23.0/123456789/messages')
        self.assertNotIn(TOKEN,request.full_url)
        self.assertEqual(request.get_header('Authorization'),'Bearer '+TOKEN)
        payload=json.loads(request.data)
        self.assertEqual(payload['type'],'template')
        self.assertEqual(payload['to'],CONFIG['recipient'])
        self.assertEqual(payload['template']['language'],{'code':'pt_BR'})
        self.assertEqual(payload['template']['components'],[{'type':'body','parameters':[{'type':'text','text':'Queda Teste de envio'}]}])
        self.assertIsInstance(builder.call_args.args[0],whatsapp_meta.NoRedirect)

    def test_rejects_redirect_even_with_a_success_body(self):
        redirect=whatsapp_meta.NoRedirect()
        self.assertIsNone(redirect.redirect_request(None,None,302,'Found',{},'https://other.invalid'))
        error=HTTPError('https://graph.facebook.com',302,'Found',{},io.BytesIO(b'{}'))
        with patch.object(whatsapp_meta,'build_opener') as builder:
            builder.return_value.open.side_effect=error
            with self.assertRaises(whatsapp_meta.SendError) as result: whatsapp_meta.send(CONFIG,TOKEN,'Teste')
        self.assertFalse(result.exception.retryable)

    def test_known_errors_have_safe_actionable_messages(self):
        for status,code,retryable,expected in [(401,190,False,'token'),(400,132001,False,'Modelo'),
                (400,132000,False,'variável'),(400,131026,False,'Destino'),(429,130429,True,'Limite'),(500,1,True,'temporariamente')]:
            with self.subTest(code=code):
                body=json.dumps({'error':{'code':code,'message':TOKEN}}).encode()
                error=HTTPError('https://graph.facebook.com',status,'Error',{},io.BytesIO(body))
                with patch.object(whatsapp_meta,'build_opener') as builder:
                    builder.return_value.open.side_effect=error
                    with self.assertRaises(whatsapp_meta.SendError) as result: whatsapp_meta.send(CONFIG,TOKEN,'Teste')
                self.assertEqual(result.exception.retryable,retryable)
                self.assertIn(expected,str(result.exception))
                self.assertNotIn(TOKEN,str(result.exception))

    def test_connection_failure_is_retryable_and_tls_verification_failure_is_not(self):
        for cause,retryable in [(OSError('fake-token'),True),(ssl.SSLCertVerificationError('fake-token'),False)]:
            with patch.object(whatsapp_meta,'build_opener') as builder:
                builder.return_value.open.side_effect=URLError(cause)
                with self.assertRaises(whatsapp_meta.SendError) as result: whatsapp_meta.send(CONFIG,TOKEN,'Teste')
            self.assertEqual(result.exception.retryable,retryable)
            self.assertNotIn('fake-token',str(result.exception))

    def test_no_acceptance_id_or_oversized_body_is_not_reported_as_sent(self):
        for payload in [{'ok':True},{'messages':[]},{'messages':[{'id':''}]},{'messages':[1]}]:
            with patch.object(whatsapp_meta,'build_opener') as builder:
                builder.return_value.open.return_value=self.response(payload)
                with self.assertRaises(whatsapp_meta.SendError): whatsapp_meta.send(CONFIG,TOKEN,'Teste')
        with patch.object(whatsapp_meta,'MAX_RESPONSE',10),patch.object(whatsapp_meta,'build_opener') as builder:
            builder.return_value.open.return_value=self.response({'messages':[{'id':'too-big'}]})
            with self.assertRaises(whatsapp_meta.SendError): whatsapp_meta.send(CONFIG,TOKEN,'Teste')

    def test_network_boundary_rejects_custom_urls_and_header_injection(self):
        for config,token in [(dict(CONFIG,phone_number_id='../anything'),TOKEN),
                (dict(CONFIG,api_version='https://other.invalid'),TOKEN),(CONFIG,'token\r\nOther: secret')]:
            with patch.object(whatsapp_meta,'build_opener') as builder:
                with self.assertRaises(whatsapp_meta.SendError): whatsapp_meta.send(config,token,'Teste')
                builder.assert_not_called()

    def test_summary_is_plain_bounded_text_and_keeps_both_transition_types(self):
        events=[dict(level=level,device_name='BBU\nCentro',host='192.0.2.10',message='Mensagem\t  de teste',event_at='2026-11-01T12:00:00+00:00') for level in ['critical','success','warning']]
        result=whatsapp_meta.summary(events)
        self.assertIn('QUEDA',result); self.assertIn('RECUPERAÇÃO',result)
        self.assertIn('UTC',result)
        self.assertNotIn('\n',result); self.assertNotIn('\t',result)
        self.assertLessEqual(len(result),900)
