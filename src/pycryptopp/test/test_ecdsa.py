import random
import base64

import os
SEED = os.environ.get('REPEATABLE_RANDOMNESS_SEED', None)

if SEED is None:
    # Generate a seed which is fairly short (to ease cut-and-paste, writing it
    # down, etc.).  Note that Python's random module's seed() function is going
    # to take the hash() of this seed, which is a 32-bit value (currently) so
    # there is no point in making this seed larger than 32 bits.  Make it 30
    # bits, which conveniently fits into six base-32 chars.  Include a separator
    # because chunking facilitates memory (including working and short-term
    # memory) in humans.
    chars = "ybndrfg8ejkmcpqxot1uwisza345h769" # Zooko's choice, rationale in "DESIGN" doc in z-base-32 project
    SEED = ''.join([random.choice(chars) for x in range(3)] + ['-'] + [random.choice(chars) for x in range(3)])

import logging
logging.info("REPEATABLE_RANDOMNESS_SEED: %s\n" % SEED)
logging.info("In order to reproduce this run of the code, set the environment variable \"REPEATABLE_RANDOMNESS_SEED\" to %s before executing.\n" % SEED)
random.seed(SEED)

def seed_which_refuses(a):
    logging.warn("I refuse to reseed to %s -- I already seeded with %s.\n" % (a, SEED,))
    return
random.seed = seed_which_refuses

from random import randrange

import unittest

from pycryptopp.publickey import ecdsa

def randstr(n, rr=randrange):
    return ''.join([chr(rr(0, 256)) for x in range(n)])

from base64 import b32encode
def ab(x): # debuggery
    if len(x) >= 3:
        return "%s:%s" % (len(x), b32encode(x[-3:]),)
    elif len(x) == 2:
        return "%s:%s" % (len(x), b32encode(x[-2:]),)
    elif len(x) == 1:
        return "%s:%s" % (len(x), b32encode(x[-1:]),)
    elif len(x) == 0:
        return "%s:%s" % (len(x), "--empty--",)

def div_ceil(n, d):
    """
    The smallest integer k such that k*d >= n.
    """
    return (n/d) + (n%d != 0)

KEYBITS =256

SEEDBITS=256
SEEDBYTES=div_ceil(SEEDBITS, 8)

# The number of bytes required to encode a public key in this elliptic curve.
PUBKEYBYTES=div_ceil(KEYBITS, 8)+1 # 1 byte for the sign of the y component

# The number of bytes requires to encode a signature in this elliptic curve.
SIGBITS=KEYBITS*2
SIGBYTES=div_ceil(SIGBITS, 8)

class Signer(unittest.TestCase):
    def test_construct(self):
        seed = randstr(SEEDBYTES)
        ecdsa.SigningKey(seed)

    def test_sign(self):
        seed = randstr(SEEDBYTES)
        signer = ecdsa.SigningKey(seed)
        sig = signer.sign("message")
        self.assertEqual(len(sig), SIGBYTES)

    def test_sign_and_verify(self):
        seed = randstr(SEEDBYTES)
        signer = ecdsa.SigningKey(seed)
        sig = signer.sign("message")
        v = signer.get_verifying_key()
        self.assertTrue(v.verify("message", sig))

    def test_sign_and_verify_emptymsg(self):
        seed = randstr(SEEDBYTES)
        signer = ecdsa.SigningKey(seed)
        sig = signer.sign("")
        v = signer.get_verifying_key()
        self.assertTrue(v.verify("", sig))

    def test_construct_from_same_seed_is_reproducible(self):
        seed = randstr(SEEDBYTES)
        signer1 = ecdsa.SigningKey(seed)
        signer2 = ecdsa.SigningKey(seed)
        self.assertEqual(signer1.get_verifying_key().serialize(), signer2.get_verifying_key().serialize())

        # ... and using different seeds constructs a different private key.
        seed3 = randstr(SEEDBYTES)
        assert seed3 != seed, "Internal error in Python random module's PRNG (or in pycryptopp's hacks to it to facilitate testing) -- got two identical strings from randstr(%s)" % SEEDBYTES
        signer3 = ecdsa.SigningKey(seed3)
        self.assertNotEqual(signer1.get_verifying_key().serialize(), signer3.get_verifying_key().serialize())

        # Also try the all-zeroes string just because bugs sometimes are
        # data-dependent on zero or cause bogus zeroes.
        seed4 = '\x00'*SEEDBYTES
        assert seed4 != seed, "Internal error in Python random module's PRNG (or in pycryptopp's hacks to it to facilitate testing) -- got the all-zeroes string from randstr(%s)" % SEEDBYTES
        signer4 = ecdsa.SigningKey(seed4)
        self.assertNotEqual(signer4.get_verifying_key().serialize(), signer1.get_verifying_key().serialize())

        signer5 = ecdsa.SigningKey(seed4)
        self.assertEqual(signer5.get_verifying_key().serialize(), signer4.get_verifying_key().serialize())

    def test_construct_short_seed(self):
        try:
            ecdsa.SigningKey("\x00\x00\x00")
        except ecdsa.Error as le:
            self.assertTrue("seed is required to be of length " in str(le), le)
        else:
           self.fail("Should have raised error from seed being too short.")

    def test_construct_bad_arg_type(self):
        try:
            ecdsa.SigningKey(1)
        except TypeError as le:
            self.assertTrue("must be string" in str(le), le)
        else:
           self.fail("Should have raised error from seed being of the wrong type.")

class Verifier(unittest.TestCase):
    def test_from_signer_and_serialize_and_deserialize(self):
        seed = randstr(SEEDBYTES)
        signer = ecdsa.SigningKey(seed)

        verifier = signer.get_verifying_key()
        s1 = verifier.serialize()
        self.assertEqual(len(s1), PUBKEYBYTES)
        ecdsa.VerifyingKey(s1)
        s2 = verifier.serialize()
        self.assertEqual(s1, s2)

def flip_one_bit(s):
    assert s
    i = randrange(0, len(s))
    result = s[:i] + chr(ord(s[i])^(0x01<<randrange(0, 8))) + s[i+1:]
    assert result != s, "Internal error -- flip_one_bit() produced the same string as its input: %s == %s" % (result, s)
    return result

def randmsg():
    # Choose a random message size from a range probably large enough to
    # exercise any different code paths which depend on the message length.
    randmsglen = randrange(1, SIGBYTES*2+2)
    return randstr(randmsglen)

class SignAndVerify(unittest.TestCase):
    def _help_test_sign_and_check_good_keys(self, signer, verifier):
        msg = randmsg()

        sig = signer.sign(msg)
        self.assertEqual(len(sig), SIGBYTES)
        self.assertTrue(verifier.verify(msg, sig))

        # Now flip one bit of the signature and make sure that the signature doesn't check.
        badsig = flip_one_bit(sig)
        self.assertFalse(verifier.verify(msg, badsig))

        # Now generate a random signature and make sure that the signature doesn't check.
        badsig = randstr(len(sig))
        assert badsig != sig, "Internal error -- randstr() produced the same string twice: %s == %s" % (badsig, sig)
        self.assertFalse(verifier.verify(msg, badsig))

        # Now flip one bit of the message and make sure that the original signature doesn't check.
        badmsg = flip_one_bit(msg)
        self.assertFalse(verifier.verify(badmsg, sig))

        # Now generate a random message and make sure that the original signature doesn't check.
        badmsg = randstr(len(msg))
        assert badmsg != msg, "Internal error -- randstr() produced the same string twice: %s == %s" % (badmsg, msg)
        self.assertFalse(verifier.verify(badmsg, sig))

    def _help_test_sign_and_check_bad_keys(self, signer, verifier):
        """
        Make sure that this signer/verifier pair cannot produce and verify signatures.
        """
        msg = randmsg()

        sig = signer.sign(msg)
        self.assertEqual(len(sig), SIGBYTES)
        self.assertFalse(verifier.verify(msg, sig))

    def test(self):
        seed = randstr(SEEDBYTES)
        signer = ecdsa.SigningKey(seed)
        verifier = signer.get_verifying_key()
        self._help_test_sign_and_check_good_keys(signer, verifier)

        vstr = verifier.serialize()
        self.assertEqual(len(vstr), PUBKEYBYTES)
        verifier2 = ecdsa.VerifyingKey(vstr)
        self._help_test_sign_and_check_good_keys(signer, verifier2)

        signer2 = ecdsa.SigningKey(seed)
        self._help_test_sign_and_check_good_keys(signer2, verifier2)

        verifier3 = signer2.get_verifying_key()
        self._help_test_sign_and_check_good_keys(signer, verifier3)

        # Now test various ways that the keys could be corrupted or ill-matched.

        # Flip one bit of the public key.
        badvstr = flip_one_bit(vstr)
        try:
            badverifier = ecdsa.VerifyingKey(badvstr)
        except ecdsa.Error:
            # Ok, fine, the verifying key was corrupted and Crypto++ detected this fact.
            pass
        else:
            self._help_test_sign_and_check_bad_keys(signer, badverifier)

        # Randomize all bits of the public key.
        badvstr = randstr(len(vstr))
        assert badvstr != vstr, "Internal error -- randstr() produced the same string twice: %s == %s" % (badvstr, vstr)
        try:
            badverifier = ecdsa.VerifyingKey(badvstr)
        except ecdsa.Error:
            # Ok, fine, the key was corrupted and Crypto++ detected this fact.
            pass
        else:
            self._help_test_sign_and_check_bad_keys(signer, badverifier)

        # Flip one bit of the private key.
        badseed = flip_one_bit(seed)
        badsigner = ecdsa.SigningKey(badseed)
        self._help_test_sign_and_check_bad_keys(badsigner, verifier)

        # Randomize all bits of the private key.
        badseed = randstr(len(seed))
        assert badseed != seed, "Internal error -- randstr() produced the same string twice: %s == %s" % (badseed, seed)
        badsigner = ecdsa.SigningKey(badseed)
        self._help_test_sign_and_check_bad_keys(badsigner, verifier)

class Compatibility(unittest.TestCase):
    def test_compatibility(self):
        # Confirm that the KDF used by the SigningKey constructor doesn't
        # change without suitable backwards-compability
        seed = 'bd616451f65d151ddd63efef42202c13457d1a0a44fb6f642be4bf9567ef19c6'.decode('hex')
        signer = ecdsa.SigningKey(seed)
        v1 = signer.get_verifying_key()
        vs = v1.serialize()
        vs32 = base64.b32encode(vs)
        self.assertEqual(vs32, "AIWKEM44YHQCR3VI7SF7IJI7SSW6YNLMGMWBIXQWXC5522H2KXXHO===")
        v2 = ecdsa.VerifyingKey(vs)
        # print signer.sign("message").encode('hex')
        sig = 'a914953c6e6cecaf97d3d7f142ed1da88014752c3e1cd43b38f3327a73be67075bda7ec4a2ead5bb8a3471271a44ffbbd456b4d3ca470584c05703fdbe7b5bc0'.decode('hex')
        self.assertTrue(v1.verify("message", sig))
        self.assertTrue(v2.verify("message", sig))

if __name__ == "__main__":
    unittest.main()
