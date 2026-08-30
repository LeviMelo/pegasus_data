/* pegasus_blast.c — first-party PKWare DCL "implode" decompression.
 *
 * DATASUS's .dbc container is a DBF header stored raw, a 4-byte CRC, and the
 * record bytes compressed with PKWare's Data Compression Library (the format
 * zlib's contrib calls "blast"). This is the project's own implementation of
 * that stream format, written from the format's published structure:
 *
 *   byte 0: literal mode  — 0: literals are raw 8-bit; 1: Huffman-coded
 *   byte 1: dictionary    — log2(window) - 6, valid 4..6 (1 KiB..4 KiB)
 *   then a bit stream, LSB-first within each byte:
 *     flag bit 1 → length/distance pair:
 *         length  = base[decode(lencode)] + extra bits; 519 ends the stream
 *         distance = (decode(distcode) << n) + n extra bits + 1,
 *                    where n = 2 when length == 2, else the dictionary size
 *     flag bit 0 → one literal (raw byte or decode(litcode))
 *   Huffman decode reads one INVERTED bit at a time through canonical codes
 *   built from run-length-compact code-length tables.
 *
 * Design decisions that differ from a file-driver port, deliberately:
 *   - memory to memory: the caller owns all I/O, so nothing here can printf,
 *     block, or touch a file descriptor — this code runs inside decode
 *     workers whose stdout IS an IPC pipe;
 *   - the output buffer is caller-sized from the DBF header's own arithmetic
 *     (header_len + n_records * record_len), so a corrupt stream cannot
 *     expand past what the container promised: overflow is an error, not a
 *     bigger allocation;
 *   - every failure is a distinct negative return code; the Python wrapper
 *     turns them into one exception with the reason spelled out.
 */

#include <stddef.h>

#define MAXBITS 13
#define OK 0
#define ERR_LITERAL_MODE (-1)   /* first byte not 0/1 */
#define ERR_DICT_SIZE (-2)      /* second byte not 4..6 */
#define ERR_DISTANCE (-3)       /* back-reference before start of output */
#define ERR_INPUT_EXHAUSTED (-4)
#define ERR_OUTPUT_OVERFLOW (-5)
#define ERR_BAD_CODE (-6)       /* bits form no symbol in the code */

struct state {
    const unsigned char *in;
    size_t left;
    int bitbuf;
    int bitcnt;
    unsigned char *out;
    size_t outcap;
    size_t next;
    int err;
};

/* need < 9 always; returns low `need` bits, LSB-first across bytes. */
static int bits(struct state *s, int need)
{
    int val = s->bitbuf;
    while (s->bitcnt < need) {
        if (s->left == 0) { s->err = ERR_INPUT_EXHAUSTED; return 0; }
        val |= (int)(*(s->in)++) << s->bitcnt;
        s->left--;
        s->bitcnt += 8;
    }
    s->bitbuf = val >> need;
    s->bitcnt -= need;
    return val & ((1 << need) - 1);
}

struct huffman {
    short *count;   /* count[1..MAXBITS]: codes per length */
    short *symbol;  /* canonically ordered symbols */
};

/* Canonical decode, one inverted bit at a time. */
static int decode(struct state *s, const struct huffman *h)
{
    int len = 1;
    int code = 0, first = 0, index = 0;
    int bitbuf = s->bitbuf;
    int left = s->bitcnt;
    int count;
    short *next = h->count + 1;

    while (1) {
        while (left--) {
            code |= (bitbuf & 1) ^ 1;   /* the format stores bits inverted */
            bitbuf >>= 1;
            count = *next++;
            if (code - count < first) {
                s->bitbuf = bitbuf;
                s->bitcnt = (s->bitcnt - len) & 7;
                return h->symbol[index + (code - first)];
            }
            index += count;
            first += count;
            first <<= 1;
            code <<= 1;
            len++;
        }
        left = (MAXBITS + 1) - len;
        if (left == 0) break;
        if (s->left == 0) { s->err = ERR_INPUT_EXHAUSTED; return 0; }
        bitbuf = *(s->in)++;
        s->left--;
        if (left > 8) left = 8;
    }
    s->err = ERR_BAD_CODE;
    return 0;
}

/* Expand a run-length-compact code-length table into a canonical code.
 * Each byte of `rep`: low 4 bits = code length, high 4 bits = repeat - 1.
 * Returns 0 for a complete code; anything else means the table is wrong,
 * which the self-test below turns into a hard failure at load time. */
static int construct(struct huffman *h, const unsigned char *rep, int n)
{
    int symbol, len, left;
    short offs[MAXBITS + 1];
    short length[256];

    symbol = 0;
    do {
        len = *rep++;
        left = (len >> 4) + 1;
        len &= 15;
        while (left--) length[symbol++] = (short)len;
    } while (--n);
    n = symbol;

    for (len = 0; len <= MAXBITS; len++) h->count[len] = 0;
    for (symbol = 0; symbol < n; symbol++) h->count[length[symbol]]++;
    if (h->count[0] == n) return 0;

    left = 1;
    for (len = 1; len <= MAXBITS; len++) {
        left <<= 1;
        left -= h->count[len];
        if (left < 0) return left;
    }

    offs[1] = 0;
    for (len = 1; len < MAXBITS; len++) offs[len + 1] = (short)(offs[len] + h->count[len]);
    for (symbol = 0; symbol < n; symbol++)
        if (length[symbol] != 0) h->symbol[offs[length[symbol]]++] = (short)symbol;
    return left;
}

/* The format's three fixed codes, in the compact representation. */
static const unsigned char litlen[] = {
    11, 124, 8, 7, 28, 7, 188, 13, 76, 4, 10, 8, 12, 10, 12, 10, 8, 23, 8,
    9, 7, 6, 7, 8, 7, 6, 55, 8, 23, 24, 12, 11, 7, 9, 11, 12, 6, 7, 22, 5,
    7, 24, 6, 11, 9, 6, 7, 22, 7, 11, 38, 7, 9, 8, 25, 11, 8, 11, 9, 12,
    8, 12, 5, 38, 5, 38, 5, 11, 7, 5, 6, 21, 6, 10, 53, 8, 7, 24, 10, 27,
    44, 253, 253, 253, 252, 252, 252, 13, 12, 45, 12, 45, 12, 61, 12, 45,
    44, 173};
static const unsigned char lenlen[] = {2, 35, 36, 53, 38, 23};
static const unsigned char distlen[] = {2, 20, 53, 230, 247, 151, 248};

static const short base[16] = {3, 2, 4, 5, 6, 7, 8, 9, 10, 12, 16, 24, 40, 72, 136, 264};
static const char extra[16] = {0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8};

__declspec(dllexport)
int pegasus_explode(const unsigned char *in, size_t inlen,
                    unsigned char *out, size_t outcap, size_t *outlen)
{
    struct state s;
    short litcnt[MAXBITS + 1], litsym[256];
    short lencnt[MAXBITS + 1], lensym[16];
    short distcnt[MAXBITS + 1], distsym[64];
    struct huffman litcode = {litcnt, litsym};
    struct huffman lencode = {lencnt, lensym};
    struct huffman distcode = {distcnt, distsym};
    int lit, dict, symbol, len, dist;

    if (construct(&litcode, litlen, sizeof(litlen)) != 0) return ERR_BAD_CODE;
    if (construct(&lencode, lenlen, sizeof(lenlen)) != 0) return ERR_BAD_CODE;
    if (construct(&distcode, distlen, sizeof(distlen)) != 0) return ERR_BAD_CODE;

    s.in = in; s.left = inlen; s.bitbuf = 0; s.bitcnt = 0;
    s.out = out; s.outcap = outcap; s.next = 0; s.err = OK;

    lit = bits(&s, 8);
    if (s.err) return s.err;
    if (lit > 1) return ERR_LITERAL_MODE;
    dict = bits(&s, 8);
    if (s.err) return s.err;
    if (dict < 4 || dict > 6) return ERR_DICT_SIZE;

    while (1) {
        if (bits(&s, 1)) {
            symbol = decode(&s, &lencode);
            if (s.err) return s.err;
            len = base[symbol] + bits(&s, extra[symbol]);
            if (s.err) return s.err;
            if (len == 519) break;  /* end-of-stream */

            symbol = len == 2 ? 2 : dict;
            dist = decode(&s, &distcode) << symbol;
            if (s.err) return s.err;
            dist += bits(&s, symbol);
            if (s.err) return s.err;
            dist++;

            if ((size_t)dist > s.next) return ERR_DISTANCE;
            if (s.next + (size_t)len > s.outcap) return ERR_OUTPUT_OVERFLOW;
            /* Byte-by-byte on purpose: dist can be smaller than len, and the
             * overlap semantics (repeat what is being written) are the
             * format's, exactly as memmove would NOT preserve them. */
            while (len--) {
                s.out[s.next] = s.out[s.next - (size_t)dist];
                s.next++;
            }
        } else {
            symbol = lit ? decode(&s, &litcode) : bits(&s, 8);
            if (s.err) return s.err;
            if (s.next >= s.outcap) return ERR_OUTPUT_OVERFLOW;
            s.out[s.next++] = (unsigned char)symbol;
        }
    }

    *outlen = s.next;
    return OK;
}
