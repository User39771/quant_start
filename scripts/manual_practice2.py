import math
import numpy as np
import scipy.stats as scs
import statsmodels.api as sm
from pylab import mpl,plt
#plt.style.use('seaborn')
mpl.rcParams['font.family'] = 'serif'
def gen_paths(S0,r,sigma,T,M,I):
    '''
    Generate Monte Carlo paths for geometric Brownian motion.
                Parameters
                ==========
                S0: float
                    initial stock/index value
                r: float
                    constant short rate
                sigma: float
                    constant volatility
                T: float
                    final time horizon
                M: int
                    number of time steps/intervals
                I: int
                    number of paths to be simulated
                Returns
                =======
                paths: ndarray, shape (M + 1, I)
                    simulated paths given the parameters
    '''
    dt = T / M
    paths = np.zeros((M + 1,I))
    paths[0] = S0
    for t in range(1,M + 1):
        rand = np.random.standard_normal(I)
        rand = (rand - rand.mean()) / rand.std()
        #Vectorized Euler discretization of geometric Brownian motion.
        paths[t] = paths[t - 1] * np.exp((r - 0.5 * sigma ** 2) * dt + sigma * math.sqrt(dt) * rand)
    return paths
S0 = 100.
r = 0.05
sigma = 0.2
T = 1.0
M = 50
I = 250000
np.random.seed(1000)
paths = gen_paths(S0,r,sigma,T,M,I)
print(S0 * math.exp(r * T))
print(paths[-1].mean())
plt.figure(figsize=(10,6))
plt.plot(paths[:,:10])
plt.xlabel('time steps')
plt.ylabel('index level')
print(paths[:,0].round(4))
log_returns = np.log(paths[1:] / paths[:-1])
print(log_returns[:,0].round(4))
print(scs.describe(log_returns.flatten()))
print(log_returns.mean() * M + 0.5 * sigma ** 2)
print(log_returns.std() * math.sqrt(M))
