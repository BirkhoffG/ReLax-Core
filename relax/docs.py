# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/00_docs.ipynb.

# %% ../nbs/00_docs.ipynb 3
from __future__ import annotations
from .import_essentials import *
import nbdev
from fastcore.basics import AttrDict
from fastcore.utils import *

from nbdev.showdoc import *
from nbdev.doclinks import *
from inspect import isclass
from nbdev.showdoc import (
    _ext_link, 
    _wrap_sig, 
    _fmt_anno, 
    _f_name, 
    DocmentTbl, 
    _maybe_nm, 
    _show_param
)
from nbdev.config import get_config

# %% auto 0
__all__ = ['ListDocment', 'CustomizedMarkdownRenderer']

# %% ../nbs/00_docs.ipynb 4
def _docment_parser(parser: BaseParser):
    p = parser.schema()['properties']
    if hasattr(parser, '__annotations__'):
        anno = parser.__annotations__
    else:
        anno = { k: inspect._empty for k in p.keys() }
    d = { 
        k: {
            'anno': anno[k],
            'default': v['default'] if 'default' in v else inspect._empty,
            'docment': v['description'] if 'description' in v else inspect._empty,
        } for k, v in p.items()
    }
    

    d = AttrDict(d)
    return d


# %% ../nbs/00_docs.ipynb 5
class ParserMarkdownRenderer(BasicMarkdownRenderer):
    def __init__(self, sym, name: str | None = None, title_level: int = 3):
        super().__init__(sym, name, title_level)
        self.dm.dm = _docment_parser(sym)

# %% ../nbs/00_docs.ipynb 6
def _italic(s: str): return f'<em>{s}</em>' if s.strip() else s

def _bold(s: str): return f'<b>{s}</b>' if s.strip() else s

# %% ../nbs/00_docs.ipynb 7
def _show_param(param):
    "Like `Parameter.__str__` except removes: quotes in annos, spaces, ids in reprs"
    kind,res,anno,default = param.kind,param._name,param._annotation,param._default
    kind = '*' if kind==inspect._VAR_POSITIONAL else '**' if kind==inspect._VAR_KEYWORD else ''
    res = kind+res
    # if anno is not inspect._empty: res += f':{_f_name(anno) or _fmt_anno(anno)}'
    if default is not inspect._empty: res += f'={_f_name(default) or repr(default)}'
    return res


def _fmt_sig(sig):
    if sig is None: return ''
    p = {k:v for k,v in sig.parameters.items()}
    _params = [_show_param(p[k]) for k in p.keys() if k != 'self']
    return "(" + ', '.join(_params)  + ")"


# %% ../nbs/00_docs.ipynb 8
def _inner_list2mdlist(l: list):
    param_name, param_anno, param_default, param_doc = l
    # annotation
    if param_anno == inspect._empty: param_anno = None
    else: param_anno = f"`{param_anno}`"
    # default value
    if param_default == inspect._empty: param_default = None
    else: param_default = _italic(f"default={param_default}")

    mdoc = ""
    if param_anno and param_default:
        mdoc += f"* {_bold(param_name)} ({param_anno}, {param_default})"
    elif param_anno:
        mdoc += f"* {_bold(param_name)} ({param_anno})"
    elif param_default:
        mdoc += f"* {_bold(param_name)} ({param_default})"
    else:
        mdoc += f"* {_bold(param_name)}"
    
    if not (param_doc == inspect._empty): 
        mdoc += f" -- {param_doc}"
    return mdoc

def _params_mdlist(tbl: DocmentTbl):
    param_list = [
        L([k, v['anno'], v['default'], v['docment']])
        for k, v in tbl.dm.items() if k != 'return'
    ]
    # param_list = tbl._row_list
    return L(param_list).map(_inner_list2mdlist)

def _return_mdlist(tbl: DocmentTbl):
    return_list = [tbl.dm['return'][k] for k in ['anno', 'default', 'docment']]
    param_anno, param_default, param_doc = return_list
    mdoc = ""
    if not param_anno == inspect._empty: 
        mdoc += f"(`{param_anno}`)"
    if param_doc != inspect._empty:
        mdoc += f" -- {param_doc}"
    return mdoc

def _show_params_return(tbl: DocmentTbl):
    if not tbl.has_docment: return ''
    doc = "" 
    doc = "::: {#docs}\n\n"
    doc += '**Parameters:**' + '\n\n\n\n'
    doc += _params_mdlist(tbl)
    doc += "\n\n:::\n\n"
    if tbl.has_return:
        doc += "::: {#docs}\n\n"
        doc += '\n\n**Returns:**\n'
        doc += f"&ensp;&ensp;&ensp;&ensp;{_return_mdlist(tbl)}"
        doc += "\n\n:::"
    
    return '\n'.join(doc)

# %% ../nbs/00_docs.ipynb 9
class ListDocment:
    def __init__(self, tbl: DocmentTbl):
        self.tbl = tbl
    
    def _repre_mardown(self):
        return _show_params_return(self.tbl)

    __str__ = _repre_mardown

# %% ../nbs/00_docs.ipynb 10
def _repr_markdown(
    renderer: ShowDocRenderer,
    use_module_dir: bool,
    show_title: bool,
    is_class: bool,
    title_level: int = 3,
):
    doc = ""
    src = NbdevLookup().code(renderer.fn)
    _look_up = NbdevLookup()[renderer.fn]
    module_dir = _look_up[1].replace('.py', '').replace('/', '.') + '.' if _look_up else ""
    link = _ext_link(src, '[source]', 'style="float:right; font-size:smaller"') + '\n\n' if src else ""
    
    name = f"{module_dir}{_bold(renderer.nm)}" if use_module_dir else _bold(renderer.nm)

    # title
    if show_title:
        h = f'h{title_level}'
        doc += f"""<{h} class="doc-title" id="{renderer.nm}">{name}</{h}>"""
    # signature
    doc += link
    if is_class: doc += '::: {.doc-sig}\n\n class '
    else: doc += '::: {.doc-sig}\n\n '
    doc += f"{name} {_italic(_fmt_sig(renderer.sig))}\n\n:::"
    # docs
    if renderer.docs: doc += f"\n\n{renderer.docs}"
    # params and return
    if renderer.dm.has_docment:
        doc += f"\n\n{ListDocment(renderer.dm)}"
    return doc


# %% ../nbs/00_docs.ipynb 11
class CustomizedMarkdownRenderer(ShowDocRenderer):
    """Displaying documents of functions, classes, `haiku.module`, and `BaseParser`."""
    
    def __init__(self, sym, name:str|None=None, title_level:int=3):
        super().__init__(sym, name, title_level)
        self.isclass = inspect.isclass(sym)
        self.hook_methods(sym)
        self._check_sym(sym)

    def hook_methods(self, sym):
        self.methods = []
        if self.isclass and hasattr(sym, '__ALL__'):
            all_methods_syms_names = [
                (getattr(sym, x), x) for x in sym.__ALL__
            ]
            self.methods = [ShowDocRenderer(sym, name=str(x)) for sym, x in all_methods_syms_names]

    def _check_sym(self, sym):
       
        if self.isclass:
            # extract annotations for pydantic models
            if issubclass(sym, BaseParser):
                self.dm.dm = _docment_parser(sym)
            # extract annotations for hk.Module
            # if issubclass(sym, hk.Module):
            #     _sym = sym.__init__
            #     try: self.sig = signature_ex(_sym, eval_str=True)
            #     except (ValueError,TypeError): self.sig = None
            #     self.dm = DocmentTbl(_sym)

    def _repr_markdown_(self):
        doc = _repr_markdown(
            self,
            use_module_dir=True,
            show_title=True,
            is_class=self.isclass,
            title_level=self.title_level + 1,
        )
        if self.methods:
            doc += '\n\n::: {.doc-methods} \n\n**Methods** \n\n' 
            doc += '\n\n'.join([
                _repr_markdown(
                    x, use_module_dir=False,
                    show_title=False, is_class=False,
                ) 
                for x in self.methods])
            
            doc += '\n\n:::\n\n'
            
        return doc
