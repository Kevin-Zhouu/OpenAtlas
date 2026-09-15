import { render, screen, cleanup } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { ValidationDetails } from './ValidationDetails';
afterEach(cleanup);
it('shows failed checks, reasons, expected and observed evidence across repair rounds', () => {
 render(<ValidationDetails rounds={[{round:1,status:'failed',checks:[{id:'interaction-1',title:'Interaction 1',status:'failed',expected:'Visible feedback changes',reason:'Expected #feedback to be visible',definition:{selector:'#action',expect_selector:'#feedback',action:'click'},before_text:'',duration_ms:5000},{id:'mobile',title:'Phone layout',status:'not_run',expected:'No overflow'}]},{round:2,status:'passed',checks:[{id:'interaction-1',title:'Interaction 1',status:'passed',expected:'Visible feedback changes',after_text:'Correct answer',duration_ms:300}]}]} />);
 expect(screen.getByText('Round 1')).toBeInTheDocument();
 expect(screen.getByText('Round 2')).toBeInTheDocument();
 expect(screen.getByText('Expected #feedback to be visible')).toBeVisible();
 expect(screen.getByText('Correct answer')).toBeInTheDocument();
 expect(screen.getByText('Not reached because validation stopped before this check.')).toBeInTheDocument();
 expect(screen.getByText('5.00 s')).toBeInTheDocument();
});
it('shows historical evidence without claiming individual checks passed', () => {
 render(<ValidationDetails rounds={[{round:1,status:'failed',legacy:true,reason:'<img src=x onerror=alert(1)>',checks:[]}]} />);
 expect(screen.getByText(/before detailed reporting/)).toBeInTheDocument();
 expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeVisible();
 expect(document.querySelector('img')).toBeNull();
});
