import numpy as np
import re
from math import isclose
import copy

from .element import Element
from .material_solver import MaterialSolver
from .. import ParameterTable, RowCollector
from ..units import Quantity, Unit

class Compound:
    natural: bool
    elements: dict
    M: Quantity
    rho: Quantity = None
    V: Quantity = None
    n: Quantity = None
    
    @staticmethod
    def from_elements(elements:list, natural:bool=True):
        compound = Compound(natural=natural)
        for el in elements:
            compound.add_element(el)
        return compound
        
    def atom(self, expression:str):
        if m:=re.match("[0-9]+(\.[0-9]+|)([eE]{1}[+-]?[0-9]{0,3}|)",expression):
            return float(expression)
        else:
            return Compound.from_elements([
                Element(expression, natural=self.natural),
            ], natural=self.natural)
            
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
            
    def __init__(self, expression:str=None, natural:bool=True):
        self.natural = natural
        self.elements = {}
        if expression and expression!='':
            with MaterialSolver(self.atom) as ms:
                compound = ms.solve(expression)
            for expr, el in compound.elements.items():
                self.elements[expr] = el
        self.M = np.sum([e.A for e in self.elements.values()])

    def __str__(self):
        elements = []
        for expr, el in self.elements.items():
            element = f"{expr}" 
            if el.count>1:
                element += f"{int(el.count):d}"
            elements.append(element)
        elements = " ".join(elements)
        data = self.data_compound(quantity=False)
        p = int(round(data['sum']['Z']))
        n = data['sum']['N']
        e = int(round(data['sum']['e']))
        A = data['sum']['A']
        return f"Compound(p={p:d} n={n:.03f} e={e:d} A={A:.03f})"
        
    def __mul__(self, other:float):
        compound = copy.deepcopy(self)
        compound.elements = {}
        for expr in self.elements.keys():
            el = self.elements[expr] * other
            compound.add_element(el)
        return compound
    
    def __add__(self, other):
        compound = copy.deepcopy(self)
        compound.elements = {}
        for expr,el in self.elements.items():
            compound.add_element(el)
        if isinstance(other, Compound):
            for expr,el in other.elements.items():
                compound.add_element(el)
        elif isinstance(other, Element):
            compound.add_element(other)
        return compound
    
    def add_element(self, element:Element):
        expr = element.expression
        if self.rho:
            element.set_density(self.n)
        if expr in self.elements:
            self.elements[expr] += element
        else:
            self.elements[expr] = element
        self.M = np.sum([e.A for e in self.elements.values()])
    
    def set_amount(self, rho:Quantity, V:Quantity=None):
        self.rho = rho
        self.n = (rho/self.M).rebase()
        for s in self.elements.keys():
            self.elements[s].set_density(self.n)
        self.V = V
            
    def data_elements(self, quantity=True):
        with ParameterTable(['element','isotope','ionisation','A','Z','N','e'], #,'A_nuc','E_bin'], 
                keys=True, keyname='expression') as pt:
            for s,e in self.elements.items():
                el = Element(s, natural=self.natural)
                #A_nuc = Quantity(el.Z, '[m_p]') + Quantity(el.N, '[m_n]')
                #E_bin = ((A_nuc-el.A)*Unit('[c]')**2)/(el.Z+el.N)
                pt[s] = [
                    el.element, 
                    el.isotope, 
                    el.ionisation, 
                    el.A.to('Da') if quantity else el.A.value('Da'), 
                    el.Z, 
                    el.N, 
                    el.e, 
                    #A_nuc.value('Da'), 
                    #E_bin.value('MeV'),
                ]
            return pt
            
    def data_compound(self, part:list=None, quantity=True):
        if not self.elements:
            return None
        columns = ['A','Z','N','e']
        if self.rho:
            columns += ['n','rho','X']
        if self.V:
            columns += ['n_V','M_V']
        with ParameterTable(['count']+columns, keys=True, keyname='expression') as pt:
            rc = RowCollector(['count']+columns)
            for s,e in self.elements.items():
                if part and s not in part:
                    continue
                row = [
                    e.count, 
                    e.A.to('Da') if quantity else e.A.value('Da'), 
                    e.Z, 
                    e.N, 
                    e.e, 
                ]
                if self.rho:
                    row += [
                        e.n.to('cm-3') if quantity else e.n.value('cm-3'), 
                        e.rho.to('g/cm3') if quantity else e.rho.value('g/cm3'),
                        (e.rho/self.rho).to('%') if quantity else (e.rho/self.rho).value('%'),
                    ]
                if self.V:
                    row += [
                        (e.n*self.V).value(),
                        (e.rho*self.V).to('g') if quantity else (e.rho*self.V).value('g'),
                    ]
                pt[s] = row
                rc.append(row)
            avg = [np.average(rc['count'])]
            sum = [np.sum(rc['count'])]
            for p in columns:
                sum.append(np.sum(rc[p]))
                avg.append(np.average(np.divide(rc[p],rc['count']), weights=rc['count']))
            pt['avg'] = avg
            pt['sum'] = sum
            return pt
            
    def print(self):
        text = []
        text.append("Properties:\n")
        text.append(f"Molecular mass: {self.M}")
        if self.rho:
            text.append(f"Mass density: {self.rho}")
            text.append(f"Molecular density: {self.n}")
        text.append("")
        text.append("Elements:\n")
        df = self.data_elements(quantity=False).to_dataframe()
        df = df.rename(columns={"A": "A[Da]", "A_nuc": "A_nuc[Da]", "E_bin": "E_bin[MeV]"})
        text.append(df.to_string(index=False))
        text.append("")
        text.append("Compound:\n")
        df = self.data_compound(quantity=False).to_dataframe()
        df = df.rename(columns={"A": "A[Da]"})
        if self.rho:
            df = df.rename(columns={"n": "n[cm-3]", "rho": "rho[g/cm3]", "X": "X[%]"})
        if self.V:
            df = df.rename(columns={"M_V": "M_V[g]"})
        text.append(df.to_string(index=False))
        text = "\n".join(text)
        print(text)
        return text