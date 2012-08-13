#!/usr/bin/env python

"""
Model of C3 photosynthesis, this is passed to fitting function and we are 
optimising Jmax25, Vcmax25, Rd, Eaj, Eav, deltaS

That's all folks.
"""
__author__ = "Martin De Kauwe"
__version__ = "1.0 (13.08.2012)"
__email__ = "mdekauwe@gmail.com"

import sys
import numpy as np
import os


class FarquharC3(object):
    """
    Rate of photosynthesis in a leaf depends on the the rates of 
    carboxylation (Ac) and the regeneration of ribulose-1,5-bisphosphate (RuBP) 
    catalysed by the enzyme RUBISCO (Aj). This class returns the net leaf 
    photosynthesis (An) which is the minimum of this two limiting processes 
    less the rate of mitochondrial (dark) respiration (Rd). We are ignoring the
    the "export" limitation (Ap) which could occur under high levels of 
    irradiance.
    
    Model assumes conductance between intercellular space and the site of 
    carboxylation is zero. The models parameters Vcmax, Jmax, Rd along with
    the calculated values for Kc, Ko and gamma star all vary with temperature.
    The parameters Jmax and Vcmax are typically fitted with a temperature 
    dependancy function, either an exponential Arrheniuous or a peaked 
    function, i.e. the Arrhenious function with a switch off point.
    
    
    All calculations in Kelvins...
    
    References:
    -----------
    * De Pury and Farquhar, G. D. (1997) Simple scaling of photosynthesis from 
      leaves to canopies without the errors of big-leaf models. Plant Cell and
      Environment, 20, 537-557.
    * Farquhar, G.D., Caemmerer, S. V. and Berry, J. A. (1980) A biochemical 
      model of photosynthetic CO2 assimilation in leaves of C3 species. Planta,
      149, 78-90. 
    * Medlyn, B. E., Dreyer, E., Ellsworth, D., Forstreuter, M., Harley, P.C., 
      Kirschbaum, M.U.F., Leroux, X., Montpied, P., Strassemeyer, J., 
      Walcroft, A., Wang, K. and Loustau, D. (2002) Temperature response of 
      parameters of a biochemically based model of photosynthesis. II. 
      A review of experimental data. Plant, Cell and Enviroment 25, 1167-1179.
    """
    
    def __init__(self, peaked_Jmax=False, peaked_Vcmax=False):
        """
        Parameters
        ----------
        Oi : float
            intercellular concentration of O2 [mmol mol-1]
        gamstar25 : float
            co2 compensation point (i.e. the value of Ci at which net CO2 
            uptake is zero due to photorespiration) in the absence of 
            dark resp at 25 degC [umol mol-1] or 298 K
        Kc25 : float
            Michaelis-Menten coefficents for carboxylation by Rubisco at 
            25degC [umol mol-1] or 298 K
        Ko25: float
            Michaelis-Menten coefficents for oxygenation by Rubisco at 
            25degC [umol mol-1]. Note value in Bernacchie 2001 is in mmol!!
            or 298 K
        Ec : float
            Activation energy for carboxylation [J mol-1]
        Eo : float
            Activation energy for oxygenation [J mol-1]
        Egamma : float
            Activation energy at CO2 compensation point [J mol-1]
        R : float
            Universal gas constant [J mol-1 K-1]
        theta : float
            Curvature of the light response
        alpha : float
            Leaf quantum yield (initial slope of the A-light response curve)
        peaked_Jmax : logical
            Use the peaked Arrhenius function (if true)
        peaked_Vcmax : logical
            Use the peaked Arrhenius function (if true)
        """
        self.Oi = 205.0     
        self.gamstar25 = 42.75 
        self.Kc25 = 404.9      
        self.Ko25 = 278.4   
        self.Ec = 79430.0      
        self.Eo = 36380.0      # Note there is a typo in the R mate code here...  
        self.Egamma = 37830.0  
        self.RGAS = 8.314      
        self.theta = 0.9995 # was 0.9 - is too low for the hyperbolic minimum     
        self.alpha = 0.3 * 0.8 # quantum yield x absorptance (Medlyn et al 2002)     
        self.edj = 200000.0
        self.edv = 200000.0
        self.deg2kelvin = 273.15
        self.peaked_Jmax = peaked_Jmax
        self.peaked_Vcmax = peaked_Vcmax
        
    def calc_photosynthesis(self, par, Ci, Tleaf, Jmax=None, Vcmax=None, 
                            Jmax25=None, Vcmax25=None, Q10=None, Eaj=None, 
                            Eav=None, deltaSj=None, deltaSv=None, r25=None):
        """
        Parameters
        ----------
        par : float
            PAR [umol m-2 time unit-1]
        Ci : float
            intercellular CO2 concentration [umol mol-1]
        Tleaf : float
            leaf temp [deg K]
        
        * Optional args:
        Jmax : float
            potential rate of electron transport at measurement temperature 
            [deg K]
        Vcmax : float
            max rate of rubisco activity at measurement temperature [deg K]
        Jmax25 : float
            potential rate of electron transport at 25 deg or 298 K
        Vcmax25 : float
            max rate of rubisco activity at 25 deg or 298 K
        Q10 : float
            ratio of respiration at a given temperature divided by respiration 
            at a temperature 10 degrees lower
        Eaj : float
            activation energy for the parameter [kJ mol-1]
        Eav : float
            activation energy for the parameter [kJ mol-1]
        deltaSj : float
            entropy factor [J mol-1 K-1)
        deltaSv : float
            entropy factor [J mol-1 K-1)
        r25 : float
            Estimate of respiration rate at the reference temperature 25 deg C
             or 298 K [deg K]
        
        
        Returns:
        --------
        An : float
            Net leaf assimilation rate [umol m-2 s-1]
        Acn : float
            Net rubisco-limited leaf assimilation rate [umol m-2 s-1]
        Ajn : float
            Net RuBP-regeneration-limited leaf assimilation rate [umol m-2 s-1]
        """
        self.check_supplied_args(Jmax, Vcmax, Jmax25, Vcmax25, r25)
        
        # Michaelis-Menten constant for O2/CO2, Arrhenius temp dependancy
        Kc = self.arrh(self.Kc25, self.Ec, Tleaf)
        Ko = self.arrh(self.Ko25, self.Eo, Tleaf)
        Km = Kc * (1.0 + self.Oi / Ko)
        
        # Effect of temp on CO2 compensation point 
        gamma_star = self.arrh(self.gamstar25, self.Egamma, Tleaf)
        
        # Calculations at 25 degrees C or the measurement temperature.
        if r25 is not None and Jmax25 is not None and Vcmax25 is not None:
            Rd = self.resp(Tleaf, Q10, r25, Tref=25.0)
        
            # Effect of temperature on Vcmax and Jamx
            if self.peaked_Vcmax:
                Vcmax = self.peaked_arrh(Vcmax25, Eav, Tleaf, deltaSv, self.edv)
            else:
                Vcmax = self.arrh(Vcmax25, Eav, Tleaf)
            
            if self.peaked_Jmax:
                Jmax = self.peaked_arrh(Jmax25, Eaj, Tleaf, deltaSj, self.edj)
            else:
                Jmax = self.arrh(Jmax25, Eaj, Tleaf)
        
        # actual rate of electron transport, a function of absorbed PAR
        J = self.quadratic(a=self.theta, b=-(self.alpha * par + Jmax), 
                           c=self.alpha * par * Jmax)
                           
        # Rubisco-limited photosynthesis
        Ac = (Vcmax * (Ci - gamma_star)) / (Ci + Km)
        
        # rate of photosynthesis when RuBP-regeneration is limiting
        Aj = (J / 4.0) * ((Ci - gamma_star) / (Ci + 2.0 * gamma_star))
       
        # Photosynthesis estimated using hyperbolic minimum of Ac and Aj to
        # effectively smooth over discontinuity when moving from light/electron 
        # transport limited to rubisco limited photosynthesis
        # except if Ci < 150 in which case it is always Rubisco limited
        arg = ((Ac + Aj - np.sqrt((Ac + Aj)**2 - 4.0 * self.theta * Ac * Aj)) / 
              (2.0 * self.theta))
        A = np.where(Ci < 150, Ac, arg)
        A = np.where(Ci > np.max(Ci) - 10.0, Aj, A)
       
        # net assimilation rates.
        An = A - Rd
        Acn = Ac - Rd
        Ajn = Aj - Rd
        
        return An, Acn, Ajn
         
    def check_supplied_args(self, Jmax, Vcmax, Jmax25, Vcmax25, r25):
        """ Check the user supplied arguments, either they supply the values
        at 25 deg C, or the supply Jmax and Vcmax at the measurement temp. It
        is of course possible they accidentally supply both or a random 
        combination, so raise an exception if so """
        try:
            if (r25 is not None and 
                Jmax25 is not None and 
                Vcmax25 is not None and
                Vcmax is None and 
                Jmax is None):
                return
            elif (r25 is None and 
                  Jmax25 is None and 
                  Vcmax25 is None and
                  Vcmax is not None and 
                  Jmax is not None):
                return
        except AttributeError:
            err_msg = "Supplied arguments are a mess!"
            raise AttributeError, err_msg      
        
    def quadratic(self, a, b, c):
        """ minimilist quadratic solution as root for J solution should always
        be positive, so I have excluded other quadratic solution steps. If 
        roots for J are negative or equal to zero then the data is bogus """
       
        # solve quadratic and return smallest root...
        root = b**2 - 4.0 * a * c    
        x = np.where(root > 0.0, (-b + np.sqrt(root)) / (2.0 * a), -9999.9)
        y = np.where(root > 0.0, (-b - np.sqrt(root)) / (2.0 * a), -9999.9)
        x = np.ma.masked_where(y < -9000.0, y)
        y = np.ma.masked_where(y < -9000.0, y)
        
        return np.minimum(x, y)
    
    def arrh(self, k25, Ea, Tk):
        """ Temperature dependence of kinetic parameters is described by an
        Arrhenius function.    

        Parameters:
        ----------
        k25 : float
            rate parameter value at 25 degC or 298 K
        Ea : float
            activation energy for the parameter [kJ mol-1]
        Tk : float
            leaf temperature [deg K]

        Returns:
        -------
        kt : float
            temperature dependence on parameter 
        
        References:
        -----------
        * Medlyn et al. 2002, PCE, 25, 1167-1179.   
        """
        return k25 * np.exp((Ea * (Tk - 298.15)) / (298.15 * self.RGAS * Tk)) 
    
    def peaked_arrh(self, k25, Ea, Tk, deltaS, Hd):
        """ Temperature dependancy approximated by peaked Arrhenius eqn, 
        accounting for the rate of inhibition at higher temperatures. 

        Parameters:
        ----------
        k25 : float
            rate parameter value at 25 degC or 298 K
        Ea : float
            activation energy for the parameter [kJ mol-1]
        Tk : float
            leaf temperature [deg K]
        deltaS : float
            entropy factor [J mol-1 K-1)
        Hd : float
            describes rate of decrease about the optimum temp [KJ mol-1]
        
        Returns:
        -------
        kt : float
            temperature dependence on parameter 
        
        References:
        -----------
        * Medlyn et al. 2002, PCE, 25, 1167-1179. 
        
        """
        arg1 = self.arrh(k25, Ea, Tk)
        arg2 = 1.0 + np.exp((298.15 * deltaS - Hd) / (298.15 * self.RGAS))
        arg3 = 1.0 + np.exp((Tk * deltaS - Hd) / (Tk * self.RGAS))
        
        return arg1 * arg2 / arg3
   
        
    def resp(self, Tleaf, Q10, r25, Tref=25.0):
        """ Calculate leaf respiration accounting for temperature dependence.
        
        Parameters:
        ----------
        r25 : float
            Estimate of respiration rate at the reference temperature 25 deg C
            or or 298 K
        Tref : float
            reference temperature
        Q10 : float
            ratio of respiration at a given temperature divided by respiration 
            at a temperature 10 degrees lower
        
        Returns:
        -------
        Rt : float
            leaf respiration
        
        References:
        -----------
        Tjoelker et al (2001) GCB, 7, 223-230.
        """
        return r25 * Q10**(((Tleaf - self.deg2kelvin) - Tref) / 10.0)
        