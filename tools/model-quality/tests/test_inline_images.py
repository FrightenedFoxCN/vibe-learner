import base64
import struct
import time
import unittest
import random
import zlib
from tests import test_infrastructure as infrastructure
config = infrastructure.config
from model_quality.ledger import GateClosed
from model_quality.transport import MeteredTransport

PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6zAAAAABJRU5ErkJggg=='

class InlineImageTests(unittest.TestCase):
    setUp = infrastructure.InfrastructureTests.setUp
    tearDown = infrastructure.InfrastructureTests.tearDown
    def payload(self, url=None):
        return {'model':'MiniMax-M3','max_tokens':256,'messages':[{'role':'user','content':[
            {'type':'text','text':'Read the synthetic image.'},
            {'type':'image_url','image_url':{'url':url or 'data:image/png;base64,'+PNG}}]}]}

    def test_opt_in_image_records_only_integrity_metadata(self):
        c=config(max_inline_images=1)
        MeteredTransport(c,self.ledger,'image',time.monotonic()+200).request(self.payload())
        with self.ledger.transaction() as db:
            import json
            meta=json.loads(db.execute('select metadata from wires').fetchone()[0])
        self.assertEqual(meta['image_count'],1)
        self.assertEqual(meta['images'][0]['width'],1)
        self.assertNotIn(PNG,str(meta))

    def test_rejected_images_do_not_reserve(self):
        c=config(max_inline_images=1)
        bad=bytearray(base64.b64decode(PNG)); bad[16:20]=struct.pack('>I',1025)
        for url in ['https://example.com/image.png','data:image/jpeg;base64,'+PNG,
                    'data:image/png;base64,!!!','data:image/png;base64,'+base64.b64encode(bad).decode(),
                    'data:image/png;base64,'+'a'*50000]:
            with self.assertRaises(GateClosed):
                MeteredTransport(c,self.ledger,'bad',time.monotonic()+200).request(self.payload(url))
        with self.assertRaises(GateClosed):
            MeteredTransport(config(),self.ledger,'default',time.monotonic()+200).request(self.payload())
        self.assertEqual(self.ledger.snapshot()['wire_count'],0)

    def test_book_page_requires_explicit_limits_and_full_reservation(self):
        def chunk(name, body):
            return struct.pack('>I',len(body))+name+body+struct.pack('>I',zlib.crc32(name+body))
        rng=random.Random(912)
        scan=b''.join(b'\x00'+rng.randbytes(30)+b'\x00'*75 for _ in range(1179))
        png=(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',833,1179,1,0,0,0,0))+
             chunk(b'IDAT',zlib.compress(scan))+chunk(b'IEND',b''))
        payload=self.payload('data:image/png;base64,'+base64.b64encode(png).decode())
        for limits in ({}, {'max_inline_image_bytes':524288},
                       {'max_inline_image_bytes':524288,'max_inline_image_dimension':2048}):
            with self.assertRaises(GateClosed):
                MeteredTransport(config(max_inline_images=1,**limits),self.ledger,'blocked',time.monotonic()+200).request(payload)
        self.assertEqual(self.ledger.snapshot()['wire_count'],0)
        c=config(max_inline_images=1,max_inline_image_bytes=524288,
                 max_inline_image_dimension=2048,input_reservation_tokens=90000)
        MeteredTransport(c,self.ledger,'page',time.monotonic()+200).request(payload)
        self.assertEqual(self.ledger.snapshot()['wire_count'],1)
