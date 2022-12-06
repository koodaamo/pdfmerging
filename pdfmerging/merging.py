import sys
import os
from argparse import ArgumentParser, FileType, Action
from enum import Enum
from itertools import chain
from pathlib import Path
from functools import cache

import yaml
import fitz
from fitz.fitz import Document
from fitz import Point, sRGB_to_pdf
from fitz import TEXT_ALIGN_LEFT, TEXT_ALIGN_RIGHT, TEXT_ALIGN_CENTER


fitz.TOOLS.set_subset_fontnames(True)

NAMESPACES = {
   'xmp': "http://ns.adobe.com/xap/1.0/",
   'rdf': "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
   'x': "adobe:ns:meta/",
   'pdf': "http://ns.adobe.com/pdf/1.3/",
   'dc': "http://purl.org/dc/elements/1.1/"
}

ALIGNMENTS = {
   "left": TEXT_ALIGN_LEFT,
   "right": TEXT_ALIGN_RIGHT,
   "center": TEXT_ALIGN_CENTER
}

class MergeField(yaml.YAMLObject):

   yaml_tag = "MergeField"

   def __init__(self, spec):
      self.page = spec["page"]
      self.text = spec["text"][1:-1]
      if self.text[0] == '<':
         self.align = "left"
         self.text = self.text[1:]
      elif self.text[-1] == '>':
         self.align = "right"
         self.text = self.text[:-1]
      else:
         self.align = "center"
      self.size = spec["size"]
      self.font = spec["font"]
      self.color = sRGB_to_pdf(spec["color"])
      self.bbox = spec["bbox"]
      self.origin = spec["origin"]

   def __repr__(self):
      return f"<{self.text} {self.size} {self.align} {self.color} {self.font.name}>"

   def __str__(self):
      return self.text


class FontInfo(yaml.YAMLObject):

   yaml_tag = "FontInfo"

   def __init__(self, spec):
      self.ext = spec[1]
      self.type = spec[2]
      self.encoding = spec[5]
      self.ref = '/' + spec[4]
      self.localname = spec[3]
      self.name = spec[3].split('+')[1]

   def __eq__(self, otherfont):
      if isinstance(otherfont, FontInfo):
         return True if self.__hash__() == otherfont.__hash__() else False
      elif isinstance(otherfont, str):
         return True if self.localname == otherfont else False
      else:
         return False

   def __hash__(self):
      return hash((self.ext, self.type, self.encoding, self.name))

   def __repr__(self):
      encoding = f" {self.encoding}" if self.encoding else ""
      return f"<{self.name}{encoding} {self.type} .{self.ext})>"

   def __str__(self):
      return self.name


@cache
def extract_fonts(doc):
   for page in doc:
      for fontspec in page.get_fonts():
         font = FontInfo(fontspec)
         font.page = page.number
         yield font


@cache
def get_docfont(font, doc):
   for pagefont in extract_fonts(doc):
      if font == pagefont:
         return pagefont
   raise LookupError(font.name)


@cache
def get_pagefont(font, page):
   for pagefont in page.get_fonts():
      candidate = FontInfo(pagefont)
      if candidate == font:
          return candidate
   raise LookupError(font.name)


@cache
def extract_fields(doc):
   for page in doc:
      fontspecs = {fontspec[3]: fontspec for fontspec in page.get_fonts()}
      textblocks = (block for block in page.get_text("dict")["blocks"] if "lines" in block)
      lines = chain.from_iterable((textblock["lines"] for textblock in textblocks))
      spans = list(chain.from_iterable((line["spans"] for line in lines)))
      found = list((span for span in spans if span["text"][0] == "{" and span["text"][-1] == "}"))
      for fieldspec in found:
         fieldspec["page"] = page.number + 1
         fieldspec["font"] = FontInfo(fontspecs[fieldspec["font"]])
         yield MergeField(fieldspec)


class MergeData(Action):

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, dict())
        for value in values:
            key, value = value.split('=')
            getattr(namespace, self.dest)[key] = value


def merge_doc(doc, fields, data):
   for page in doc:
      pagefields = [field for field in fields if field.page == page.number + 1]
      for field in pagefields:
         try:
            content = data[field.text]
         except KeyError as exc:
            raise Exception(f"No field value given for {exc}")

         try:
            field.font = get_pagefont(field.font, page)
         except LookupError as exc:
            raise Exception(f"Font {exc} not found in document")

         try:
            page.insert_textbox(field.bbox, content, fontsize=field.size, fontname=field.font.ref, color=field.color, fill=None, render_mode=0, border_width=1, expandtabs=8, align=ALIGNMENTS[field.align], rotate=0, morph=None, stroke_opacity=1, fill_opacity=1, oc=0)
         except RuntimeError:
            print(f"doc:   {doc}\nfield: {field}\nfont:  {field.font}\nref:   {field.font.ref}\ndata:  {data}")
            raise


def merge_file(pdfpath, fieldspath, data):
   doc = fitz.open(os.fspath(pdfpath))
   with open(fieldspath) as fieldsdump:
      fields = yaml.unsafe_load(fieldsdump)
   merge_doc(doc, fields, data)
   return doc


def cmdline():

   parser = ArgumentParser(prog = 'pdfmerge', description = 'PDF merge utility tool', epilog="Warning: since 'pdfmerge fill' generates a PDF to stdout, you should usually redirect it to a file")
   parser.add_argument('-v', '--verbose', action='store_true')

   subparsers = parser.add_subparsers(dest='command', title="commands", description="Following commands are available.", help="use one of these; each is described below")

   meta = subparsers.add_parser('meta', description="Extract metadata from PDF", help='extract metadata from given PDF')
   meta.add_argument('PDFFILE', help="path to the PDF whose metadata to extract", type=FileType('r'))

   fields = subparsers.add_parser('fields', description="Extract merge fields from PDF.", help='extract merge field definitions from given PDF')
   fields.add_argument('PDFFILE', help="path to a PDF with field definitions", type=FileType('r'))

   fonts = subparsers.add_parser('fonts', description="Extract font specs from PDF.", help='extract font specs from given PDF')
   fonts.add_argument('PDFFILE', help="path to a PDF with fonts", type=FileType('r'))

   merge = subparsers.add_parser('fill', description="write out a PDF with fields filled with data", epilog="REMEMBER to redirect the output to a file. You've been warned.", help='generate a PDF using given template, merge field definitions and data')
   merge.add_argument('PDFFILE', help="path to a PDF template file", type=FileType('rb'))
   merge.add_argument('FIELDSFILE', help="path to a field definitions file", type=FileType('rb'))
   merge.add_argument('mergedata', help="data to merge as 'fieldname = value' pairs", default={}, nargs='*', action = MergeData)
   merge.add_argument('--data', help="read merge data from a file", type=FileType('r'))

   args = parser.parse_args()

   match args.command:

      case "meta":
         with fitz.open(args.PDFFILE) as doc:
            for name, value in doc.metadata.items():
               print(f"{name}: {value}")

      case "fields":
         with fitz.open(args.PDFFILE) as doc:
            print(yaml.dump(tuple(extract_fields(doc))))

      case "fonts":
         with fitz.open(args.PDFFILE) as doc:
            print(yaml.dump(tuple(extract_fonts(doc))))

      case "fill":
         fields = yaml.unsafe_load(args.FIELDSFILE)
         data = {}
         if args.data:
            data.update(yaml.unsafe_load(args.data))
            for k in data:
               data[k] = str(data[k])

         data.update(**args.mergedata)

         with fitz.open(args.PDFFILE) as doc:
            try:
               merge_doc(doc, fields, data)
            except Exception as exc:
               sys.stderr.write(str(exc) + ", exiting.\n")
               sys.exit()
            else:
               sys.stdout.buffer.write(doc.tobytes())

      case other:
         parser.print_help()


if __name__=="__main__":
   cmdline()




