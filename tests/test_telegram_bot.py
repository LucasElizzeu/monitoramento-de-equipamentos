import io
import json
import ssl
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

import telegram_bot

CONFIG = dict(chat_id='123456789')
TOKEN = '987654321:AA_fake_telegram_token_for_tests_12345'


class TelegramBotTests(unittest.TestCase):
    def response(self,payload):
        response=Mock(); response.read.return_value=json.dumps(payload).encode()
        response.__enter__=Mock(return_value=response); response.__exit__=Mock(return_value=False)
        return response

    def accepted(self,chat_id=123456789):
        return dict(ok=True,result=dict(message_id=42,chat=dict(id=chat_id)))

    def test_official_plain_text_request_and_message_confirmation(self):
        with patch.object(telegram_bot,'build_opener') as builder:
            builder.return_value.open.return_value=self.response(self.accepted())
            self.assertEqual(telegram_bot.send(CONFIG,TOKEN,'Queda\nBBU Centro'),'42')
        request=builder.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url,f'https://api.telegram.org/bot{TOKEN}/sendMessage')
        payload=json.loads(request.data)
        self.assertEqual(payload['chat_id'],'123456789')
        self.assertEqual(payload['text'],'Queda\nBBU Centro')
        self.assertNotIn('parse_mode',payload)
        self.assertEqual(payload['link_preview_options'],{'is_disabled':True})
        self.assertIsInstance(builder.call_args.args[0],telegram_bot.NoRedirect)

    def test_negative_group_id_is_supported(self):
        with patch.object(telegram_bot,'build_opener') as builder:
            builder.return_value.open.return_value=self.response(self.accepted(-1001234567890))
            self.assertEqual(telegram_bot.send(dict(chat_id='-1001234567890'),TOKEN,'Teste'),'42')

    def test_redirect_is_refused_without_forwarding_secret_url(self):
        self.assertIsNone(telegram_bot.NoRedirect().redirect_request(None,None,302,'Found',{},'https://other.invalid'))
        error=HTTPError(f'https://api.telegram.org/bot{TOKEN}',302,'Found',{},io.BytesIO(b'{}'))
        with patch.object(telegram_bot,'build_opener') as builder:
            builder.return_value.open.side_effect=error
            with self.assertRaises(telegram_bot.SendError) as result: telegram_bot.send(CONFIG,TOKEN,'Teste')
        self.assertFalse(result.exception.retryable)
        self.assertNotIn(TOKEN,str(result.exception))

    def test_errors_do_not_echo_api_description_or_token_url(self):
        for status,retryable,expected in [(401,False,'Token'),(404,False,'Token'),(403,False,'permissão'),
                (400,False,'HTTP 400'),(409,False,'webhook'),(429,True,'Limite'),(500,True,'temporariamente')]:
            with self.subTest(status=status):
                body=json.dumps(dict(ok=False,description=f'https://api.telegram.org/bot{TOKEN}',parameters={'retry_after':90})).encode()
                error=HTTPError(f'https://api.telegram.org/bot{TOKEN}',status,'Error',{},io.BytesIO(body))
                with patch.object(telegram_bot,'build_opener') as builder:
                    builder.return_value.open.side_effect=error
                    with self.assertRaises(telegram_bot.SendError) as result: telegram_bot.send(CONFIG,TOKEN,'Teste')
                self.assertEqual(result.exception.retryable,retryable)
                self.assertIn(expected,str(result.exception))
                self.assertNotIn(TOKEN,str(result.exception))
                if status==429: self.assertEqual(result.exception.retry_after,90)

    def test_ok_false_and_group_migration_are_not_successful_sends(self):
        payload=dict(ok=False,error_code=400,description=TOKEN,parameters={'migrate_to_chat_id':-100123})
        with patch.object(telegram_bot,'build_opener') as builder:
            builder.return_value.open.return_value=self.response(payload)
            with self.assertRaises(telegram_bot.SendError) as result: telegram_bot.send(CONFIG,TOKEN,'Teste')
        self.assertIn('grupo mudou',str(result.exception))
        self.assertNotIn(TOKEN,str(result.exception))

    def test_connection_and_tls_errors_preserve_verification_and_hide_url(self):
        for reason,retryable in [(OSError(TOKEN),True),(ssl.SSLCertVerificationError(TOKEN),False)]:
            with patch.object(telegram_bot,'build_opener') as builder:
                builder.return_value.open.side_effect=URLError(reason)
                with self.assertRaises(telegram_bot.SendError) as result: telegram_bot.send(CONFIG,TOKEN,'Teste')
            self.assertEqual(result.exception.retryable,retryable)
            self.assertNotIn(TOKEN,str(result.exception))

    def test_missing_invalid_or_wrong_chat_confirmation_is_not_success(self):
        for result in [None,True,{},dict(message_id=True,chat=dict(id=123456789)),dict(message_id=1,chat=dict(id=9))]:
            with patch.object(telegram_bot,'build_opener') as builder:
                builder.return_value.open.return_value=self.response(dict(ok=True,result=result))
                with self.assertRaises(telegram_bot.SendError): telegram_bot.send(CONFIG,TOKEN,'Teste')

    def test_discovery_returns_chat_metadata_only_without_acknowledging_updates(self):
        chats=[dict(id=123456789,type='private',first_name='Operador'),dict(id=-1001234567890,type='supergroup',title='Rede')]
        updates=[dict(message=dict(chat=chats[0],text='private message not to expose')),dict(message=dict(chat=chats[0],text='another secret')),dict(my_chat_member=dict(chat=chats[1]))]
        with patch.object(telegram_bot,'build_opener') as builder:
            builder.return_value.open.return_value=self.response(dict(ok=True,result=updates))
            result=telegram_bot.chats(TOKEN)
        self.assertEqual(len(result),2)
        self.assertEqual(result[0],dict(id='123456789',title='Operador',type='private'))
        self.assertNotIn('secret',json.dumps(result))
        self.assertNotIn('private message',json.dumps(result))
        payload=json.loads(builder.return_value.open.call_args.args[0].data)
        self.assertEqual(payload,dict(limit=20,timeout=0))
        self.assertNotIn('offset',payload)
        self.assertNotIn('allowed_updates',payload)

    def test_discovery_accepts_empty_updates_and_skips_malformed_entries(self):
        for updates in [[],[None,dict(message=None),dict(message=dict(chat={'id':True,'type':'private'}))]]:
            with patch.object(telegram_bot,'build_opener') as builder:
                builder.return_value.open.return_value=self.response(dict(ok=True,result=updates))
                self.assertEqual(telegram_bot.chats(TOKEN),[])

    def test_network_boundary_refuses_custom_hosts_invalid_tokens_and_chat_ids(self):
        for config,token in [(dict(chat_id='../anything'),TOKEN),(CONFIG,'https://other.invalid'),(CONFIG,TOKEN+'\r\nHeader: x')]:
            with patch.object(telegram_bot,'build_opener') as builder:
                with self.assertRaises(telegram_bot.SendError): telegram_bot.send(config,token,'Teste')
                builder.assert_not_called()

    def test_summary_has_timestamps_and_fits_telegram_limit_in_utf16(self):
        events=[dict(level=level,device_name='BBU <Centro>',host='192.0.2.10',message='Mensagem 😎'*300,event_at='2026-11-01T12:00:00+00:00') for level in ['critical','success','warning']]
        result=telegram_bot.summary(events)
        self.assertIn('QUEDA',result); self.assertIn('RECUPERAÇÃO',result)
        self.assertIn('01/11/2026 12:00 UTC',result)
        self.assertLessEqual(len(result.encode('utf-16-le'))//2,4000)
        self.assertLessEqual(len(telegram_bot.text_limit('😎'*5000).encode('utf-16-le'))//2,4000)

    def test_oversized_response_is_rejected(self):
        with patch.object(telegram_bot,'MAX_RESPONSE',10),patch.object(telegram_bot,'build_opener') as builder:
            builder.return_value.open.return_value=self.response(self.accepted())
            with self.assertRaises(telegram_bot.SendError): telegram_bot.send(CONFIG,TOKEN,'Teste')

    def test_bot_id_is_not_accepted_as_destination_and_does_not_make_request(self):
        with patch.object(telegram_bot,'build_opener') as builder:
            with self.assertRaises(telegram_bot.SendError) as result:
                telegram_bot.send(dict(chat_id=TOKEN.partition(':')[0]),TOKEN,'Teste')
            builder.assert_not_called()
        self.assertIn('ID do próprio bot',str(result.exception))
        self.assertNotIn(TOKEN,str(result.exception))

    def test_known_rejections_have_specific_safe_instructions(self):
        cases=[(400,'Bad Request: chat not found','Chat ID'),
               (403,"Forbidden: bot can't initiate conversation with a user",'/start'),
               (403,"Forbidden: bot can't send messages to bots",'outro bot'),
               (403,'Forbidden: bot was blocked by the user','Desbloqueie'),
               (403,'Forbidden: bot was kicked from the group chat','Adicione'),
               (403,'Forbidden: bot is not a member of the channel chat','Adicione'),
               (400,'Bad Request: not enough rights to send text messages to the chat','permissão'),
               (400,'Bad Request: chat_id is empty','destino está vazio'),
               (400,'Bad Request: message is too long','tamanho do texto')]
        for status,description,expected in cases:
            with self.subTest(description=description):
                payload=dict(description=description+' '+TOKEN)
                error=HTTPError(f'https://api.telegram.org/bot{TOKEN}',status,'Error',{},io.BytesIO(json.dumps(payload).encode()))
                with patch.object(telegram_bot,'build_opener') as builder:
                    builder.return_value.open.side_effect=error
                    with self.assertRaises(telegram_bot.SendError) as result:
                        telegram_bot.send(CONFIG,TOKEN,'Teste')
                self.assertIn(expected,str(result.exception))
                self.assertNotIn(TOKEN,str(result.exception))
                self.assertFalse(result.exception.retryable)
